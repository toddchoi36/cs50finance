import os
import sqlalchemy

from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

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

# Configure postgress
engine = create_engine("postgres://irqjtbltuuzxab:863ef9dfabdd7b888bc861b52d6c2bf5345dc71bafdcd5f9704b7303dbf7241b@ec2-52-23-86-208.compute-1.amazonaws.com:5432/d7smhfkgvqn5e6")
db = scoped_session(sessionmaker(bind=engine))

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/", methods=["GET", "POST"])
@login_required
def index():
    """Show portfolio of stocks"""
    if request.method == "GET":
        assets = db.execute("SELECT * FROM assets WHERE userID =:userID ORDER BY symbol", userID=session["user_id"])
        user_cash = db.execute("SELECT cash FROM users WHERE id =:id", id=session["user_id"])
        cash = user_cash[0]["cash"]

        display_assets = []
        shares_total = 0
        hope = request.form.getlist('hope[]')

        for row in assets:
            Symbol = row["Symbol"]
            Stock = lookup(Symbol) #create dictionary to look up current price for Price column
            Name = row["CompanyName"]
            Shares = row["Shares"]
            Price = float(Stock["price"])
            Total = float(Shares)*Price #Total column of table for each stock
            shares_total = shares_total + Total #total of all shares in the table... to be added with cash to generate grand total
            display_assets.append({'Symbol':Symbol, 'CompanyName':Name, 'Shares':Shares, 'Price':Price, 'Total':Total})

        grand_total = shares_total + cash
        return render_template("index.html", display_assets=display_assets, cash=cash, grand_total=grand_total, hope=hope)

    else:
        if not request.form.get("options"): #make sure to choose buy or sell
            return apology("choose buy or sell", 403)

        option = request.form['options']
        if option =="buy":
            assets = db.execute("SELECT Symbol FROM assets WHERE userID =:userID ORDER BY symbol", userID=session["user_id"])
            a = 0 #initalize buy share getlist
            for row in assets:
                Symbol = row["Symbol"]
                Stock = lookup(Symbol)
                buy_share = float(request.form.getlist("buy_sell_qty")[a])
                db.execute("UPDATE assets SET Shares = Shares + :buy_share, Price=:Price WHERE userID=:id AND Symbol=:symbol", buy_share = buy_share, id=session["user_id"], symbol=Symbol, Price=Stock["price"])

                rows = db.execute("SELECT cash FROM users WHERE id=:id", id=session["user_id"])
                cash = rows[0]["cash"]
                new_cash = cash - buy_share * float(Stock["price"])
                if new_cash < 0:
                    return apology("not enough money", 403)
                db.execute("UPDATE users SET cash =:new_cash WHERE id=:id", new_cash = new_cash, id=session["user_id"])
                db.commit()

                if buy_share != 0: #only add to history if buy qty is not 0
                    db.execute("INSERT INTO history (user_ID, Symbol, Shares, Price) VALUES(:userID, :Symbol, :buy_share, :Price)", userID=session["user_id"], Symbol=Symbol, buy_share=buy_share, Price=Stock["price"])
                    db.commit()
                a = a + 1 #increment row

            return redirect("/")

        elif option =="sell":
            assets = db.execute("SELECT * FROM assets WHERE userID =:userID ORDER BY symbol", userID=session["user_id"])
            a = 0 #initalize buy share getlist
            for row in assets:
                Symbol = row["Symbol"]
                Shares = row["Shares"]
                Stock = lookup(Symbol)
                sell_share = float(request.form.getlist("buy_sell_qty")[a])
                if Shares < sell_share:
                    return apology("not enough shares")
                elif Shares == sell_share:
                    db.execute("UPDATE assets SET Shares = Shares - :sell_share, Price=:Price WHERE userID=:id AND Symbol=:symbol", sell_share = sell_share, id=session["user_id"], symbol=Symbol, Price=Stock["price"])
                    db.execute("DELETE FROM assets WHERE userID=:id AND Symbol=:Symbol", id=session["user_id"], Symbol=Symbol)
                    db.commit()
                else:
                    db.execute("UPDATE assets SET Shares = Shares - :sell_share, Price=:Price WHERE userID=:id AND Symbol=:symbol", sell_share = sell_share, id=session["user_id"], symbol=Symbol, Price=Stock["price"])
                    db.commit()

                rows = db.execute("SELECT cash FROM users WHERE id=:id", id=session["user_id"])
                cash = rows[0]["cash"]
                new_cash = cash + sell_share * float(Stock["price"])

                db.execute("UPDATE users SET cash =:new_cash WHERE id=:id", new_cash = new_cash, id=session["user_id"])
                db.commit()
                if sell_share != 0: #only add to history if buy qty is not 0
                    db.execute("INSERT INTO history (user_ID, Symbol, Shares, Price) VALUES(:userID, :Symbol, :sell_share, :Price)", userID=session["user_id"], Symbol=Symbol, sell_share=0-float(sell_share), Price=Stock["price"])
                    db.commit()
                    
                a = a + 1 #increment to next row for getlist

            return redirect("/")





@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "GET":
        return render_template("buy.html")
    else:
        if not request.form.get("symbol"):
            return apology("enter Stock Symbol", 403)
        elif not request.form.get("shares"):
            return apology("enter number of shares", 403)
        elif not request.form.get("shares").isdigit():
            return apology("Enter Whole Number", 403)

        Symbol = request.form.get("symbol").upper()
        Stock = lookup(Symbol)
        if Stock == None:
            return apology("That Stock Symbol does not exist", 403)

        rows = db.execute("SELECT cash FROM users WHERE id=:id", id=session["user_id"])

        cash = rows[0]["cash"]
        new_cash = cash - float(request.form.get("shares")) * float(Stock["price"])
        if new_cash < 0:
            return apology("not enough money", 403)

        db.execute("UPDATE users SET cash =:new_cash WHERE id=:id", new_cash = new_cash, id=session["user_id"])
        db.commit()

        assetrow = db.execute("SELECT * FROM assets WHERE userID=:userID AND Symbol=:Symbol", userID=session["user_id"], Symbol=Symbol)
        if len(assetrow) == 0: #if not in assets table, then add
            db.execute("INSERT INTO assets(userID, Symbol, CompanyName, Shares, Price) VALUES(:userID, :Symbol, :CompanyName, :Shares, :Price)", userID=session["user_id"], Symbol=Symbol, CompanyName=Stock["name"], Shares=request.form.get("shares"), Price=Stock["price"])
            db.commit()
        else: #if stock already exsits then update
            db.execute("UPDATE assets SET Shares = Shares + :new_shares, Price=:Price WHERE userID=:id AND Symbol=:symbol", new_shares = request.form.get("shares"), id=session["user_id"], symbol=Symbol, Price=Stock["price"])
            db.commit()
        db.execute("INSERT INTO history (user_ID, Symbol, Shares, Price) VALUES(:userID, :Symbol, :Shares, :Price)", userID=session["user_id"], Symbol=Symbol, Shares=request.form.get("shares"), Price=Stock["price"])
        db.commit()
        return redirect("/")




@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    history = db.execute("SELECT * FROM history WHERE user_ID =:userID ORDER BY Transacted", userID=session["user_id"])

    display_history = []

    for row in history:
        Symbol = row["Symbol"]
        Shares = row["Shares"]
        Price = row["Price"]
        Transacted = row["Transacted"] #Total column of table for each stock

        display_history.append({'Symbol':Symbol, 'Shares':Shares, 'Price':Price, 'Transacted':Transacted})

    return render_template("history.html", display_history=display_history)

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
    """Get stock quote."""
    if request.method == "GET":
        return render_template("quote.html")
    else:
        if not request.form.get("symbol"):
            return apology("enter Stock Symbol", 403)
        elif not request.form.get("shares"):
            return apology("enter number of shares", 403)
        elif not request.form.get("shares").isdigit():
            return apology("Enter Whole Number", 403)

        Symbol = request.form.get("symbol").upper()
        Stock = lookup(Symbol)
        if Stock == None:
            return apology("That Stock Symbol does not exist", 403)

        quote_num_shares = float(request.form.get("shares")) * float(Stock["price"])



        return render_template("quoted.html", stock = Stock, quote_num_shares = quote_num_shares, shares = request.form.get("shares"))



@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method =="GET":
        return render_template("register.html")
    else:
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        if not request.form.get("password"):
            return apology("must provide password", 403)

        #password req check
        #if len(request.form.get("password")) < 6:
        #    return apology("pass length should be at least 6 char", 403)
        #if len(request.form.get("password")) > 20:
        #    return apology("pass length should not be greater than 19 char", 403)
        #if not any(char.isdigit() for char in request.form.get("password")):
        #    return apology("pass should have at least one number", 403)
        #if not any(char.isupper() for char in request.form.get("password")):
        #    return apology("pass should have at least one uppercase letter", 403)
        #if not any(char.islower() for char in request.form.get("password")):
        #    return apology("pass should have at least one lowercase letter", 403)
        #password
        if request.form.get("confirm password") != request.form.get("password"):
            return apology("passwords do not match", 403)

        if db.execute("SELECT id FROM users WHERE username=:username", {"username": request.form.get("username")}).rowcount == 0:
            primary_key = db.execute("INSERT INTO users(username, hash) VALUES(:username, :hash)", {"username": request.form.get("username"), "hash": generate_password_hash(request.form.get("password"))})        
            session["user_id"] = primary_key["id"]
            db.commit()
            return redirect("/")
        else:
            return apology("Username already taken")




@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "GET":
        return render_template("sell.html")
    else:
        if not request.form.get("symbol"):
            return apology("enter Stock Symbol", 403)
        elif not request.form.get("shares"):
            return apology("enter number of shares", 403)
        elif not request.form.get("shares").isdigit():
            return apology("Enter Whole Number", 403)

        Symbol = request.form.get("symbol").upper()
        Stock = lookup(Symbol)
        if Stock == None:
            return apology("That Stock Symbol does not exist", 403)

        rows = db.execute("SELECT cash FROM users WHERE id=:id", id=session["user_id"])
        cash = rows[0]["cash"]

        assetrows = db.execute("SELECT Shares FROM assets WHERE userID=:userID AND Symbol=:Symbol", userID=session["user_id"], Symbol=Symbol)
        if len(assetrows) == 0 or float(assetrows[0]["Shares"]) < float(request.form.get("shares")): #if not in asset table or not enough then stop
            return apology("You Do Not Have Enough Shares of This Stock")
        elif float(assetrows[0]["Shares"]) == float(request.form.get("shares")): #if selling last share, then remove it from table
            new_cash = cash + float(request.form.get("shares")) * float(Stock["price"])
            db.execute("UPDATE users SET cash =:new_cash WHERE id=:id", new_cash = new_cash, id=session["user_id"])
            db.execute("DELETE FROM assets WHERE userID=:id AND Symbol=:Symbol", id=session["user_id"], Symbol=Symbol)
            db.execute("INSERT INTO history (user_ID, Symbol, Shares, Price) VALUES(:userID, :Symbol, :Shares, :Price)", userID=session["user_id"], Symbol=Symbol, Shares=0-float(request.form.get("shares")), Price=Stock["price"])
            db.commit()
            return redirect("/")
        else:
            new_cash = cash + float(request.form.get("shares")) * float(Stock["price"]) #if not selling last share, then update Shares Column
            db.execute("UPDATE users SET cash =:new_cash WHERE id=:id", new_cash = new_cash, id=session["user_id"])
            db.execute("UPDATE assets SET Shares = Shares - :new_shares, Price=:Price WHERE userID=:id AND Symbol=:Symbol", new_shares = request.form.get("shares"), id=session["user_id"], Symbol=Symbol, Price=Stock["price"])
            db.execute("INSERT INTO history (user_ID, Symbol, Shares, Price) VALUES(:userID, :Symbol, :Shares, :Price)", userID=session["user_id"], Symbol=Symbol, Shares=0-float(request.form.get("shares")), Price=Stock["price"])
            db.commit()
            return redirect("/")



def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)

# Function to validate the password
#def password_check(passwd):

    #SpecialSym =['$', '@', '#', '%']
    #val = True

    #if len(passwd) < 6:
    #    print('length should be at least 6')
    #    val = False

    #if len(passwd) > 20:
    #    print('length should be not be greater than 8')
    #    val = False

    #if not any(char.isdigit() for char in passwd):
    #    print('Password should have at least one numeral')
    #    val = False

    #if not any(char.isupper() for char in passwd):
    #    print('Password should have at least one uppercase letter')
    #    val = False

    #if not any(char.islower() for char in passwd):
    #    print('Password should have at least one lowercase letter')
    #   val = False

    #if not any(char in SpecialSym for char in passwd):
    #    print('Password should have at least one of the symbols $@#')
    #    val = False
    #if val:
    #    return val


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
