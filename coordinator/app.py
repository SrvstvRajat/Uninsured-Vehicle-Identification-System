from flask import Flask, request, render_template_string

from query_tool import get_vehicle_status, load_master

app = Flask(__name__)

TEMPLATE = """
<!doctype html>
<html>
<head>
    <title>Vehicle Insurance Lookup</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 900px; margin: 40px auto; }
        input { padding: 10px; width: 300px; }
        button { padding: 10px 18px; }
        pre { background: #f5f5f5; padding: 20px; white-space: pre-wrap; }
    </style>
</head>
<body>
    <h2>Vehicle Insurance Lookup</h2>
    <form method="get">
        <input name="plate" placeholder="Enter vehicle plate"
               value="{{ plate or '' }}">
        <button type="submit">Search</button>
    </form>
    {% if result %}
        <h3>Result</h3>
        <pre>{{ result }}</pre>
    {% endif %}
</body>
</html>
"""


@app.route("/")
def home():
    plate = request.args.get("plate")
    result = None
    if plate:
        result = get_vehicle_status(plate, load_master())
    return render_template_string(TEMPLATE, plate=plate, result=result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False)
