import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

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
    """Show portfolio of stocks"""
    name_data = db.execute("SELECT username FROM users WHERE id = ?", session["user_id"])

    # Check if name_data is not empty and return the first result
    if name_data:
        name = name_data[0]['username']
    else:
        name = "Guest"  # Fallback if no result is found

    return render_template("homepage.html", name=name)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol").upper()
        shares = request.form.get("shares")

        # Validate inputs
        if not symbol:
            return apology("Missing stock symbol", 400)
        try:
            shares = int(shares)
            if shares <= 0:
                return apology("Invalid number of shares", 400)
        except (ValueError, TypeError):
            return apology("Invalid number of shares", 400)

        stock = lookup(symbol)
        price = stock["price"]
        total_cost = price * shares

        db.execute("INSERT INTO holdings (user_id, stock_symbol, shares, total_amount) VALUES (?, ?, ?, ?)",
                session["user_id"], symbol, shares, total_cost)
        # Insert into history table
        db.execute("INSERT INTO history (user_id, stock_symbol, shares, price, transaction_type) VALUES (?, ?, ?, ?, ?)",
                   session["user_id"], symbol, shares, price, 'BUY')

        # Return all needed values to template
        return render_template("buy.html",
                            status=stock,
                            shares=shares,
                            price=price,  # Passing the raw price
                            total_price=total_cost)
    else:
        return render_template("buy.html")


@app.route("/history", methods=["GET"])
@login_required
def history():
    """Show history of transactions"""
    # Fetch history from the database for the logged-in user
    user_history = db.execute(
        "SELECT * FROM history WHERE user_id = ? ORDER BY timestamp DESC", session["user_id"]
    )

    # Render the template and pass the history to it
    return render_template("history.html", history=user_history)


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
        ) #will get all the rows that matches query

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 403)

        # If it reaches this point, it is valid. Remember which user has logged in
        session["user_id"] = rows[0]["id"]
        print("userlogin valid")

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
    """Get stock quote."""
    if request.method == "POST":
        symbol = request.form.get("symbol")

        if not symbol:
            return apology("must provide symbol", 400)

        stock = lookup(symbol)

        if stock is None:
            return apology("invalid symbol", 400)

        return render_template("quote.html", status=stock)

    else:
        return render_template("quote.html")



@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        # Check for missing fields
        if not username:
            return apology("must provide username", 400)
        if not password:
            return apology("must provide password", 400)
        if not confirmation:
            return apology("must confirm password", 400)
        if password != confirmation:
            return apology("passwords do not match", 400)

        # Check if username already exists
        existing = db.execute("SELECT * FROM users WHERE username = ?", username)
        if len(existing) != 0:
            return apology("username already exists", 400)

        # Insert user into database
        hash_pw = generate_password_hash(password)
        db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", username, hash_pw)

        # Redirect to login
        return redirect("/login")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    # Get list of symbols the user owns (used in both GET and POST cases)
    symbols = db.execute("SELECT stock_symbol FROM holdings WHERE user_id = ?", session["user_id"])

    if request.method == "POST":
        symbol = request.form.get("symbol").upper()
        shares = request.form.get("shares")

        # Validate inputs
        if not symbol:
            return apology("Missing stock symbol", 400)
        if not shares or not shares.isdigit() or int(shares) <= 0:
            return apology("Invalid number of shares", 400)

        shares = int(shares)
        stock = lookup(symbol)

        if stock is None:
            return apology("Invalid stock symbol", 400)

        # Check user's shares
        user_shares = db.execute("SELECT shares FROM holdings WHERE user_id = ? AND stock_symbol = ?",
                                 session["user_id"], symbol)

        if not user_shares or user_shares[0]["shares"] < shares:
            return apology("Not enough shares to sell", 400)

        price = stock["price"]
        total_earned = price * shares

        # Add cash to user
        db.execute("UPDATE users SET cash = cash + ? WHERE id = ?", total_earned, session["user_id"])

        # Update or delete from holdings
        remaining_shares = user_shares[0]["shares"] - shares
        if remaining_shares == 0:
            db.execute("DELETE FROM holdings WHERE user_id = ? AND stock_symbol = ?", session["user_id"], symbol)
        else:
            db.execute("UPDATE holdings SET shares = ?, total_amount = total_amount - ? WHERE user_id = ? AND stock_symbol = ?",
                       remaining_shares, total_earned, session["user_id"], symbol)

        # Insert into history table
        db.execute("INSERT INTO history (user_id, stock_symbol, shares, price, transaction_type) VALUES (?, ?, ?, ?, ?)",
                   session["user_id"], symbol, shares, price, 'SELL')

        # After successful sale, render template with both success message and symbols
        return render_template("sell.html", shares=shares, status=stock, symbols=[row["stock_symbol"] for row in symbols])

    # GET request
    return render_template("sell.html", symbols=[row["stock_symbol"] for row in symbols])
