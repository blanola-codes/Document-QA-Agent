"""
Flask web app for the Rule-Based Document Question Answering System.

Run:
    python app.py
Then open http://127.0.0.1:5000 in your browser.

This is a single-user local app: it keeps one knowledge base in memory
(the one built from the most recently uploaded CSV file).
"""

import uuid
from pathlib import Path

from flask import Flask, jsonify, render_template, request
from werkzeug.utils import secure_filename

from document_qa import DocumentQASystem
from evaluation import SUITES, run_evaluation

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
SAMPLE_FILE = BASE_DIR / "sample_data" / "planets.csv"
UPLOAD_DIR.mkdir(exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024  # reject uploads over 1 MB

# The current document's knowledge base. Rebuilt on every upload.
STATE = {"agent": None, "filename": None}


def build_agent(csv_path, display_name):
    """Build a fresh knowledge base from a CSV file and make it the current one."""
    agent = DocumentQASystem(csv_path)
    if not agent.records:
        raise ValueError("The CSV file has a header but no data rows.")
    STATE["agent"] = agent
    STATE["filename"] = display_name
    return agent


def summary(agent):
    """Small summary of the knowledge base, shown in the dashboard."""
    return {
        "filename": STATE["filename"],
        "records": len(agent.records),
        "triples": len(agent.triples),
        "columns": agent.headers,
        "entity_column": agent.entity_column,
        "order_column": agent.order_column,
    }


def require_agent():
    """Return the current agent, or None if no document has been loaded yet."""
    return STATE["agent"]


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/upload", methods=["POST"])
def upload():
    file = request.files.get("file")
    if file is None or file.filename == "":
        return jsonify(error="Please choose a CSV file."), 400
    original_name = secure_filename(file.filename)
    if not original_name.lower().endswith(".csv"):
        return jsonify(error="Only .csv files are supported."), 400

    # Save under a random name so uploads can never overwrite each other.
    saved_path = UPLOAD_DIR / f"{uuid.uuid4().hex}.csv"
    file.save(saved_path)
    try:
        agent = build_agent(saved_path, original_name)
    except (ValueError, UnicodeDecodeError, OSError) as error:
        saved_path.unlink(missing_ok=True)
        return jsonify(error=f"Could not build the knowledge base: {error}"), 400
    return jsonify(summary(agent))


@app.route("/api/sample", methods=["POST"])
def load_sample():
    try:
        agent = build_agent(SAMPLE_FILE, "planets.csv (sample)")
    except (ValueError, OSError) as error:
        return jsonify(error=str(error)), 500
    return jsonify(summary(agent))


@app.route("/api/knowledge")
def knowledge():
    agent = require_agent()
    if agent is None:
        return jsonify(error="No document loaded yet."), 404
    data = summary(agent)
    # "triples" in the summary is the count, so the list gets its own key.
    data["triple_list"] = [
        {"subject": s, "relation": r, "object": str(o)}
        for s, r, o in agent.triples
    ]
    return jsonify(data)


@app.route("/api/graph")
def graph():
    agent = require_agent()
    if agent is None:
        return jsonify(error="No document loaded yet."), 404
    edges = [
        {"from": s, "to": str(o)}
        for s, r, o in agent.triples
        if r == "immediately_before"
    ]
    nodes = [record["name"] for record in agent.records.values()]
    return jsonify(nodes=nodes, edges=edges, order_column=agent.order_column)


@app.route("/api/ask", methods=["POST"])
def ask():
    agent = require_agent()
    if agent is None:
        return jsonify(error="Please upload a document first."), 400
    data = request.get_json(silent=True) or {}
    question = str(data.get("question", "")).strip()
    if not question:
        return jsonify(error="Please type a question."), 400
    if len(question) > 300:
        return jsonify(error="Questions can be at most 300 characters."), 400
    return jsonify(agent.answer_question(question))


@app.route("/api/evaluate")
def evaluate():
    """Run a test suite against the sample planets document.

    A fresh knowledge base is built from the sample file, so the results do
    not depend on whichever document is currently loaded.
    """
    suite = request.args.get("suite", "main")
    if suite not in SUITES:
        return jsonify(error="Unknown test suite."), 400
    try:
        agent = DocumentQASystem(SAMPLE_FILE)
        rows, metrics = run_evaluation(agent, SUITES[suite])
    except (ValueError, OSError, KeyError) as error:
        return jsonify(error=f"Could not run the evaluation: {error}"), 500
    return jsonify(metrics=metrics, rows=rows, test_file=SUITES[suite].name)


@app.errorhandler(413)
def too_large(_error):
    return jsonify(error="File is too large (limit is 1 MB)."), 413


if __name__ == "__main__":
    # debug=False: the debugger lets anyone run code on your computer.
    app.run(host="127.0.0.1", port=5000, debug=False)
