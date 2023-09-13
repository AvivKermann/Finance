import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import date
from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    stocks = db.execute(
        "SELECT stockSymbol, SUM(amount) AS amount FROM purchases WHERE  purchases.userID = (?) GROUP BY stockSymbol HAVING SUM(amount) > 0;",
        session["user_id"],
    )
    cash = db.execute("SELECT cash FROM users WHERE id = (?)", session["user_id"])[0][
        "cash"
    ]

    total_value = cash
    grand_total = cash

    for stock in stocks:
        quote = lookup(stock["stockSymbol"])
        stock["name"] = quote["name"]
        stock["price"] = quote["price"]
        stock["value"] = stock["price"] * stock["amount"]
        total_value += stock["value"]
        grand_total += stock["value"]

    return render_template(
        "index.html",
        stocks=stocks,
        cash=usd(cash),
        total_value=usd(total_value),
        grand_total=usd(grand_total),
    )


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    if request.method == "GET":
        return render_template("buy.html")
    else:
        if request.form.get("symbol") == "" or request.form.get("shares") == "":
            return apology("Values can not be empty", 400)
        elif lookup(request.form.get("symbol")) is None:
            return apology("stock not found", 400)

        else:
            stock_info = lookup(request.form.get("symbol"))
            stock_amount = request.form.get("shares")
            if not stock_amount.isdigit() or int(stock_amount) <= 0:
                return apology("Not valid amount", 400)
            stock_amount = int(stock_amount)
            stock_price = stock_info["price"]
            stock_symbol = str(stock_info["symbol"])
            cash_needed = stock_amount * stock_price
            user_cash = int(
                db.execute("SELECT cash FROM users WHERE id = (?)", session["user_id"])[
                    0
                ]["cash"]
            )

            # update DB and makes the purchase if possible.
            if cash_needed > user_cash:
                return apology("Not Enough Cash", 400)
            else:
                cash_post_purchase = user_cash - cash_needed
                db.execute(
                    "UPDATE users SET cash = (?) WHERE id = (?)",
                    cash_post_purchase,
                    session["user_id"],
                )
                db.execute(
                    "INSERT INTO purchases (userId, amount, purchasePrice, stockSymbol) VALUES (?, ?, ? , ?)",
                    session["user_id"],
                    stock_amount,
                    stock_price,
                    stock_symbol,
                )
                flash(
                    f"Bought {stock_amount} of {stock_symbol} for {usd(stock_price)} each, total of {usd(cash_needed)} spent!"
                )

                return redirect("/")


@app.route("/history")
@login_required
def history():
    stocks = db.execute(
        "SELECT stockSymbol, amount, purchasePrice, purchaseDate FROM purchases WHERE userId = (?)",
        session["user_id"],
    )
    return render_template("history.html", stocks=stocks)


@app.route("/cashgrab", methods=["POST"])
@login_required
def cashgrab():
    if request.form.get("add") is not None:
        cash_add = int(request.form.get("add"))
        cash_before = int(
            db.execute("SELECT cash FROM users WHERE id = (?)", session["user_id"])[0][
                "cash"
            ]
        )
        db.execute(
            "UPDATE users SET cash = (?) WHERE id = (?)",
            cash_before + cash_add,
            session["user_id"],
        )
        flash(
            f"Loaded {usd(cash_add)} into your account, balance is now {usd(cash_before + cash_add)}"
        )
        return redirect("/")


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    if request.method == "GET":
        return render_template("quote.html")
    else:
        if not request.form.get("symbol"):
            return apology("Please provide a stock symbol", 400)
        elif lookup(request.form.get("symbol")) is None:
            return apology("Didint find that stock, please check grammer.", 400)

        stock_symbol = request.form.get("symbol")
        stock_info = lookup(stock_symbol)
        if stock_info is None:
            return apology("No stock were found", 400)

        return render_template(
            "quoted.html",
            name=stock_info["name"],
            price=usd(stock_info["price"]),
            symbol=stock_info["symbol"],
        )


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if (
        request.method == "POST"
        and request.form.get("username") != ""
        and request.form.get("password") != ""
        or request.form.get("password") != request.form.get("confirmation")
    ):
        username = request.form.get("username")
        password = request.form.get("password")
        confirm = request.form.get("confirmation")
        phash = generate_password_hash(password)

        if db.execute("SELECT * FROM users WHERE username = (?)", username):
            return apology("Username already exist", 400)
        elif password != confirm:
            return apology("Passwords do not match", 400)
        else:
            db.execute(
                "INSERT INTO users (username, hash) VALUES (?, ?)", username, phash
            )
            return redirect("/login")

    elif request.method == "GET":
        return render_template("register.html")
    else:
        return apology("Not valid credentials", 400)


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    stocks = db.execute(
        "SELECT stockSymbol, SUM(amount) AS amount FROM purchases WHERE userId = (?) GROUP BY stockSymbol HAVING amount > 0",
        session["user_id"],
    )

    if request.method == "POST":
        symbol = request.form.get("symbol")
        amount = request.form.get("shares")

        if not symbol:
            return apology("Must provide a stock symbol")
        elif not amount or not amount.isdigit() or int(amount) <= 0:
            return apology("Amount must be a positive number")
        else:
            amount = int(amount)
        for stock in stocks:
            if stock["stockSymbol"] == symbol:
                if stock["amount"] < amount:
                    return apology("Not enough stocks")
                else:
                    quote = lookup(symbol)
                    if quote is None:
                        return apology("No stock found")
                    price = quote["price"]
                    total_sale = amount * price
                    total_sale = int(total_sale)

                    db.execute(
                        "UPDATE users SET cash = cash + (?) WHERE id = (?)",
                        total_sale,
                        session["user_id"],
                    )

                    db.execute(
                        "INSERT INTO purchases (userId, amount, purchasePrice,stockSymbol) VALUES (?, ?, ?, ?)",
                        session["user_id"],
                        -amount,
                        total_sale,
                        symbol,
                    )

                    flash(f"Sold {amount} shares of {symbol} for {usd(total_sale)}!")
                    return redirect("/")
        return apology("Symbol not found")

    else:
        return render_template("sell.html", stocks=stocks)
