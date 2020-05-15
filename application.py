import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    rows = db.execute("SELECT symbol, stock, belongings.shares FROM users JOIN belongings ON users.id=belongings.id WHERE belongings.id=:user_id;",
                        user_id=session["user_id"])
    stockCash = 0
    for row in rows:
        stockCash += row["shares"]*lookup(row["symbol"])["price"]

    lines = db.execute("SELECT cash FROM users WHERE id=:user_id;", user_id=session["user_id"])
    for line in lines:
        cash = line["cash"]

    return render_template("index.html", rows=rows, myFunction=lookup, usdFunction=usd, cash=cash, stockCASH=stockCash)

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        symbol = request.form.get("symbol")
        if not symbol:
            symbol = request.form.get("owned")
        print(symbol)
        symbol = symbol.upper()
        # Check for a number of shares to be aqcuired
        quantity = float(request.form.get("shares"))

        # Check for a valid stock symbol
        if not symbol:
            return apology("must provide a stock symbol", 403)
        elif lookup(symbol) == None:
            return apology("Stock is not listed", 403)

        # Get the stock features via lookup function
        stock = lookup(symbol)

        # Check if the chash owned is enough to perform the transaction
        rows = db.execute("SELECT * FROM users WHERE id=:user_id", user_id=session["user_id"])
        if rows[0]["cash"] < stock["price"]*quantity:
            return apology("Insufficient funds", 403)

        # Update the cash currently owned
        db.execute("UPDATE users SET cash=:value WHERE id=:user_id;",
                    user_id=session["user_id"], value=rows[0]["cash"]-(stock["price"]*quantity))

        current_time = datetime.now()
        # Insert the transaction to the history
        db.execute("INSERT INTO history (id, symbol, stock, price, shares, time) VALUES(?, ?, ?, ?, ?, ?);",
                    session["user_id"], symbol, stock["name"], stock["price"], quantity, current_time)

        # Check if the stock is already owned
        lines = db.execute("SELECT symbol FROM belongings WHERE id=:user_id;",
                    user_id=session["user_id"])
        for line in lines:
            if symbol == line["symbol"]:
                # Update the belongings
                db.execute("UPDATE belongings SET shares=shares+:shares WHERE id=:user_id AND symbol=:symbol;",
                            shares=int(quantity), user_id=session["user_id"], symbol=symbol)

                # Redirect user to home page
                return redirect("/")

        # Insert the transaction into belongings if not found in belongings
        db.execute("INSERT INTO belongings (id, symbol, stock, shares) VALUES(?, ?, ?, ?);",
                    session["user_id"], symbol, stock["name"], quantity)

        # Redirect user to home page
        return redirect("/")

    else:
        symbols = db.execute("SELECT symbol FROM belongings WHERE id=:user_id;",
                    user_id=session["user_id"])
        return render_template("buy.html", symbols=symbols)


@app.route("/history")
@login_required
def history():
    rows = db.execute("SELECT symbol, shares, price, time FROM history WHERE id=:user_id;", user_id=session["user_id"])
    return render_template("history.html", rows=rows)


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
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
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

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Lookup the symbol name in the cloud
        symbol = request.form.get("symbol")
        symbol = symbol.upper()
        stock = lookup(symbol)

        if stock != None:
            # Show the stock features in a new html
            return render_template("quoted.html", name=stock["name"], price=stock["price"], symbol=stock["symbol"])
        elif stock == None:
            return apology("Stock is not listed", 403)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Get the inputs from the user
        name = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        # Ensure username was submitted
        if not name:
            return apology("must provide username", 403)

        # Query database for username
        line = db.execute("SELECT * FROM users WHERE username = :name", name = name)
        if len(line) == 1:
            return apology("Username already taken", 403)

        # Ensure password was submitted
        if not password:
            return apology("must provide password", 403)

        # Ensure passwords match
        if not confirmation or password != confirmation:
            return apology("passwords do not match", 403)

        hash_p = generate_password_hash(password, method='pbkdf2:sha256', salt_length=12)

        # Insert the new user to the database
        db.execute("INSERT INTO users (username, hash) VALUES(?, ?)", name, hash_p)

        # Redirect user to home page
        return redirect("/login")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    if request.method == "POST":

        symbol = request.form.get("symbol")
        shares = int(request.form.get("shares"))

        # Get the stock features via lookup function
        stock = lookup(symbol)

        # Lookup the symbol name in db
        rows = db.execute("SELECT symbol, shares FROM belongings WHERE id=:user_id;", user_id=session["user_id"])
        for row in rows:
            print(row)
            if symbol == row['symbol'] and shares <= row['shares']:

                # Insert the transaction into belongings
                db.execute("UPDATE belongings SET shares=:values WHERE id=:user_id AND symbol=:symbol;",
                            values=(row["shares"]-shares), user_id=session["user_id"], symbol=symbol)

                # Update the cash currently owned
                db.execute("UPDATE users SET cash=cash+:value WHERE id=:user_id;",
                            user_id=session["user_id"], value=(stock["price"]*shares))

                current_time = datetime.now()
                # Insert the transaction to the history
                db.execute("INSERT INTO history (id, symbol, stock, price, shares, time) VALUES(?, ?, ?, ?, ?, ?);",
                    session["user_id"], symbol, stock["name"], stock["price"], (-1*shares), current_time)

                db.execute("DELETE FROM belongings WHERE shares=0;")
                return redirect("/")

        for lines in rows:
            if symbol == lines['symbol'] and shares > lines['shares']:
                return apology("You do not own that quantity of shares", 403)

    else:
        symbols = db.execute("SELECT symbol FROM belongings WHERE id=:user_id;",
                    user_id=session["user_id"])
        return render_template("sell.html", symbols=symbols)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
