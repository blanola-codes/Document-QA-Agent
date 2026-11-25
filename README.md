# Rule-Based Document Question Answering System (AID201A)

Upload a CSV document, build a knowledge base of (subject, relation, object)
triples, and ask questions answered by fixed templates, rules and breadth-first
search (BFS). No NLP, RAG, embeddings, external APIs or LLM calls are used.

## Files
- `app.py` – Flask web app (upload, ask, knowledge base, graph).
- `document_qa.py` – the question answering engine (`DocumentQASystem` class).
- `templates/index.html`, `static/style.css`, `static/script.js` – the dashboard.
- `sample_data/planets.csv` – sample document.
- `evaluation.py` – runs a test set and measures accuracy, coverage, response time and trace correctness.
- `test_questions.csv` – the main 25-question test set (with a category for each question).
- `extra_tests.csv` – 11 extra edge cases, including questions the system does not yet support.
- `uploads/` – uploaded CSV files are saved here with random names.

## Run
1. Install Python 3.
2. Install Flask: `pip install -r requirements.txt`
3. Start the app: `python app.py`
4. Open http://127.0.0.1:5000 in your browser.

To use the engine without the website:

```python
from document_qa import DocumentQASystem
agent = DocumentQASystem("sample_data/planets.csv")
print(agent.answer_question("What is the diameter of Earth?"))
```

## Evaluation
- On the website: section 5, choose a test set and click **Run evaluation**.
- On the command line: `python evaluation.py` (or `python evaluation.py extra_tests.csv`).
  This prints the metrics and saves per-question results to `evaluation_results.csv`.
- Metrics: answer accuracy, query coverage, unsupported-question rejection, response time,
  and an automatic rule-based check that each explanation trace supports its answer.
- Always report the numbers your own run prints. `extra_tests.csv` deliberately contains
  questions the system cannot answer yet ("Which planet is closest to the Sun?",
  "How far is Earth from the Sun?"), so it will not score 100%.

## CSV format
- The first column (or one named `planet`, `name` or `entity`) identifies each record.
- A numeric column named `order`, `position`, `sequence` or `rank` builds the ordering graph used for "before / after / closer" questions.
- Every record must have a unique name. Maximum file size is 1 MB.

## Supported question types
| Type | Example |
|---|---|
| Attribute lookup | What is the diameter of Earth? |
| Attribute filter | Which planets are gas giant? |
| Multi-step reasoning (BFS) | Is Earth closer to the Sun than Jupiter? |
| Yes/no lookup | Is Neptune a terrestrial planet? |
| Unsupported | What is the temperature of Earth? → "Not found in the document." |

## Notes
- The app keeps one knowledge base in memory and is meant for local, single-user use.
- Before submission: practise explaining every function for the viva, take your own screenshots, and report only real test results.
