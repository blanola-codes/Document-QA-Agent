"""
Evaluation module for the Rule-Based Document Question Answering System.

It runs a CSV of test questions through the system and measures:
  1. Answer accuracy      - does the answer match the expected answer?
  2. Query coverage       - how many supported questions were answered at all?
  3. Response time        - average, median and slowest time per question.
  4. Reasoning correctness - does the explanation trace support the answer?
     (checked automatically with simple rules, see trace_supports_answer)

Run from the command line:
    python evaluation.py                     # main 25-question test set
    python evaluation.py extra_tests.csv     # extra edge cases

The command-line run also writes the results to evaluation_results.csv.
"""

import csv
import statistics
import sys
from pathlib import Path

from document_qa import DocumentQASystem

BASE_DIR = Path(__file__).resolve().parent
SAMPLE_FILE = BASE_DIR / "sample_data" / "planets.csv"
SUITES = {
    "main": BASE_DIR / "test_questions.csv",
    "extra": BASE_DIR / "extra_tests.csv",
}
NOT_FOUND = "Not found in the document."

# The system reports its own question type; this maps it to a test category.
TYPE_TO_CATEGORY = {
    "simple lookup": "attribute lookup",
    "attribute filter": "attribute filter",
    "multi-step reasoning": "multi-step reasoning",
    "yes/no lookup": "yes/no lookup",
    "not found": "unsupported",
}


def answer_matches(expected, answer):
    """Compare a system answer with the expected result.

    - "Yes" / "No"      : the answer must start with that word.
    - "Not found ..."   : the answer must be exactly that sentence.
    - "A, B, C"         : a list; the answer must name exactly those items.
    - "part 1 | part 2" : every part must appear in the answer.
    - anything else     : exact match.
    """
    expected, answer = expected.strip(), answer.strip()
    if expected in ("Yes", "No"):
        return answer.startswith(expected + ".")
    if expected == NOT_FOUND:
        return answer == NOT_FOUND
    if " | " in expected:
        return all(part.strip() in answer for part in expected.split(" | "))
    if "," in expected and not expected.endswith("."):
        if ": " not in answer:
            return False
        listed = answer.rsplit(": ", 1)[1].rstrip(".")
        wanted = {item.strip() for item in expected.split(",")}
        given = {item.strip() for item in listed.split(",")}
        return wanted == given
    return expected == answer


def trace_supports_answer(agent, question, result):
    """Automatic check that the explanation trace backs up the answer.

    This is a simple rule-based check, not a proof of correctness:
      - lookups / yes-no : every triple in the trace (subject, relation, value)
        must have its subject and value appear in the answer text.
      - filter           : the trace must mention a filter on a column.
      - multi-step       : a "Yes" needs a BFS path whose two ends are the
        entities in the question; a "No" needs a "no path" / same-record note.
      - unsupported      : the trace must say no template matched.
    """
    kind, answer, trace = result["type"], result["answer"], result["trace"]
    if not trace:
        return False

    if kind in ("simple lookup", "yes/no lookup"):
        for line in trace:
            parts = line.strip("()").split(", ", 2)
            if len(parts) != 3:
                return False
            subject, _relation, value = parts
            if subject not in answer or value not in answer:
                return False
        return True

    if kind == "attribute filter":
        return trace[0].startswith("Filtered triples with relation has_")

    if kind == "multi-step reasoning":
        if answer.startswith("Yes."):
            if not trace[0].startswith("BFS path: "):
                return False
            path = [step.strip().lower() for step in trace[0][len("BFS path: "):].split("->")]
            mentioned = {name.lower() for name in agent._find_entities(question.lower())}
            return len(path) >= 2 and {path[0], path[-1]} == mentioned
        return trace[0].startswith(("No directed path", "Both names refer"))

    if kind == "not found":
        return trace[0].startswith("No supported question template")
    return False


def run_evaluation(agent, test_file):
    """Run every question in test_file and return (rows, metrics)."""
    with open(test_file, newline="", encoding="utf-8") as file:
        tests = list(csv.DictReader(file))

    rows = []
    for test in tests:
        result = agent.answer_question(test["Question"])
        expected = test["Expected result"]
        rows.append({
            "No": test["No"],
            "Category": test["Category"],
            "Question": test["Question"],
            "Expected": expected,
            "System answer": result["answer"],
            "Question type": result["type"],
            "Type correct": TYPE_TO_CATEGORY.get(result["type"]) == test["Category"],
            "Correct": answer_matches(expected, result["answer"]),
            "Trace supports answer": trace_supports_answer(agent, test["Question"], result),
            "Response time (ms)": result["time_ms"],
        })
    return rows, compute_metrics(rows)


def percent(part, whole):
    return round(100 * part / whole, 1) if whole else None


def compute_metrics(rows):
    """Turn per-question rows into summary numbers."""
    total = len(rows)
    correct = sum(r["Correct"] for r in rows)

    supported = [r for r in rows if r["Category"] != "unsupported"]
    unsupported = [r for r in rows if r["Category"] == "unsupported"]
    answered = sum(r["System answer"] != NOT_FOUND for r in supported)
    rejected = sum(r["System answer"] == NOT_FOUND for r in unsupported)

    by_category = {}
    for row in rows:
        entry = by_category.setdefault(row["Category"], {"total": 0, "correct": 0})
        entry["total"] += 1
        entry["correct"] += row["Correct"]
    for entry in by_category.values():
        entry["accuracy"] = percent(entry["correct"], entry["total"])

    times = [r["Response time (ms)"] for r in rows]
    return {
        "total": total,
        "correct": correct,
        "accuracy": percent(correct, total),
        "supported_total": len(supported),
        "supported_answered": answered,
        "coverage": percent(answered, len(supported)),
        "unsupported_total": len(unsupported),
        "unsupported_rejected": rejected,
        "rejection_rate": percent(rejected, len(unsupported)),
        "type_correct": sum(r["Type correct"] for r in rows),
        "reasoning_correct": sum(r["Trace supports answer"] for r in rows),
        "reasoning_accuracy": percent(sum(r["Trace supports answer"] for r in rows), total),
        "avg_time_ms": round(statistics.mean(times), 4) if times else None,
        "median_time_ms": round(statistics.median(times), 4) if times else None,
        "max_time_ms": round(max(times), 4) if times else None,
        "by_category": by_category,
    }


def write_results_csv(rows, path):
    """Save per-question results (used as evidence in the report)."""
    with open(path, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: ("Yes" if v is True else "No" if v is False else v)
                             for k, v in row.items()})


def main():
    test_file = Path(sys.argv[1]) if len(sys.argv) > 1 else SUITES["main"]
    agent = DocumentQASystem(SAMPLE_FILE)
    rows, metrics = run_evaluation(agent, test_file)

    for row in rows:
        mark = "PASS" if row["Correct"] else "FAIL"
        print(f"{mark}  Q{row['No']:>2}  {row['Question']}")
        if not row["Correct"]:
            print(f"        expected: {row['Expected']}")
            print(f"        got:      {row['System answer']}")

    m = metrics
    print(f"\nTest file: {test_file.name}")
    print(f"Answer accuracy:      {m['correct']}/{m['total']} = {m['accuracy']}%")
    print(f"Query coverage:       {m['supported_answered']}/{m['supported_total']} = {m['coverage']}%")
    print(f"Unsupported rejected: {m['unsupported_rejected']}/{m['unsupported_total']}")
    print(f"Question type right:  {m['type_correct']}/{m['total']}")
    print(f"Reasoning (trace):    {m['reasoning_correct']}/{m['total']} = {m['reasoning_accuracy']}%")
    print(f"Response time (ms):   avg {m['avg_time_ms']}, median {m['median_time_ms']}, max {m['max_time_ms']}")
    for name, entry in m["by_category"].items():
        print(f"  {name:<22} {entry['correct']}/{entry['total']}")

    # The main test set keeps the familiar file name; other sets get their own.
    if test_file.resolve() == SUITES["main"].resolve():
        output = BASE_DIR / "evaluation_results.csv"
    else:
        output = BASE_DIR / f"evaluation_results_{test_file.stem}.csv"
    write_results_csv(rows, output)
    print(f"\nPer-question results saved to {output.name}")


if __name__ == "__main__":
    main()
