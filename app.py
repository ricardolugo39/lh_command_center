from flask import Flask

app = Flask(__name__)

@app.route("/")
def home():
    return """
    <h1>Commercial Command Center</h1>
    <p>Version 0.1</p>
    <p>Sprint 0</p>
    """

if __name__ == "__main__":
    app.run(debug=True)