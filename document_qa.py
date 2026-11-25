"""
AID201A Assignment 1
Rule-Based Document Question Answering System

The system reads a structured CSV file, converts its records into
(subject, relation, object) triples, builds an ordering graph when an
order column is available, and answers questions using fixed templates,
BFS, and rule-based matching.

No NLP, RAG, embeddings, external APIs, or LLM calls are used.
Run:
    python document_qa.py
Or use the class from another Python file:
    from document_qa import DocumentQASystem
    agent = DocumentQASystem("planets.csv")
    print(agent.answer_question("What is the diameter of Earth?"))
"""

import csv
import math
import re
import time
from collections import defaultdict, deque
from pathlib import Path


def parse_value(value):
    """Convert simple numeric CSV values to numbers; keep other values as text."""
    value = value.strip()
    if value == "":
        return value
    try:
        number = float(value)
    except ValueError:
        return value
    if not math.isfinite(number):          # keep words like "nan" or "inf" as text
        return value
    # Keep the document's own style: "3" stays 3, but "1.0" stays 1.0.
    if number.is_integer() and "." not in value and "e" not in value.lower():
        return int(number)
    return number


def normalise(text):
    """Make a field name or question phrase easier to compare."""
    return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()


class DocumentQASystem:
    """A reusable question-answering agent built from one uploaded CSV document."""

    def __init__(self, csv_path):
        self.csv_path = Path(csv_path)
        self.triples = []
        self.records = {}
        self.headers = []
        self.entity_column = None
        self.order_column = None
        self.graph = defaultdict(list)
        self._load_knowledge_base()

    def _load_knowledge_base(self):
        """Read the CSV and convert every record field into a knowledge triple."""
        if not self.csv_path.is_file():
            raise FileNotFoundError(f"CSV file not found: {self.csv_path}")

        with self.csv_path.open(newline="", encoding="utf-8-sig") as file:
            reader = csv.DictReader(file)
            if not reader.fieldnames:
                raise ValueError("The CSV file is empty or has no header row.")

            self.headers = [header.strip() for header in reader.fieldnames]
            if len(set(self.headers)) != len(self.headers):
                raise ValueError("CSV column names must be unique.")

            # Prefer a column named planet, name, or entity; otherwise use column 1.
            header_lookup = {normalise(h): h for h in self.headers}
            self.entity_column = next(
                (header_lookup[key] for key in ("planet", "name", "entity")
                 if key in header_lookup),
                self.headers[0]
            )
            self.order_column = next(
                (header_lookup[key] for key in ("order", "position", "sequence", "rank")
                 if key in header_lookup),
                None
            )

            for row_number, raw_row in enumerate(reader, start=2):
                entity = (raw_row.get(self.entity_column) or "").strip()
                if not entity:
                    raise ValueError(f"Missing entity value in CSV row {row_number}.")

                values = {
                    header: parse_value((raw_row.get(header) or ""))
                    for header in self.headers
                    if header != self.entity_column
                }
                key = entity.lower()
                if key in self.records:
                    raise ValueError(f"Duplicate entity '{entity}' in the CSV file.")

                self.records[key] = {"name": entity, **values}
                for field, value in values.items():
                    self.triples.append((entity, "has_" + field, value))

        # Create directed edges between consecutive records by their order value.
        if self.order_column and self.records:
            try:
                ordered = sorted(
                    self.records.values(),
                    key=lambda record: float(record[self.order_column])
                )
            except (TypeError, ValueError, KeyError):
                raise ValueError(
                    f"Column '{self.order_column}' must contain numeric values "
                    "to build the ordering graph."
                )

            for nearer, farther in zip(ordered, ordered[1:]):
                self.triples.append(
                    (nearer["name"], "immediately_before", farther["name"])
                )
                self.graph[nearer["name"].lower()].append(farther["name"].lower())

    def _find_entities(self, question):
        """Find every entity mentioned in a question, in the order they appear.

        If the same entity is mentioned twice (e.g. "Earth ... than Earth")
        it is returned twice, so the caller can detect that case.
        """
        question = question.lower()
        found = []
        for record in self.records.values():
            pattern = r"\b" + re.escape(record["name"].lower()) + r"\b"
            for match in re.finditer(pattern, question):
                found.append((match.start(), record["name"]))
        return [name for _, name in sorted(found)]

    def _find_attributes(self, question):
        """Identify every CSV column whose words appear in the question."""
        q_words = set(normalise(question).split())
        matched = []
        for field in self.headers:
            if field == self.entity_column:
                continue
            field_words = set(normalise(field).split())
            # Also recognise common unit suffixes, e.g. diameter_km -> diameter.
            field_words.update(
                word for word in re.findall(r"[a-z]+", field.lower())
                if word not in {"km", "au", "m", "kg"}
            )
            if q_words.intersection(field_words):
                matched.append(field)
        return matched

    def _find_value(self, question, field):
        """Find a value of this column that appears as whole words in the question."""
        values = {
            str(record[field]).lower() for record in self.records.values()
        }
        for value in sorted(values, key=len, reverse=True):
            if value and re.search(r"\b" + re.escape(value) + r"\b", question):
                return value
        return None

    def _is_planet_data(self):
        """True when the CSV is about planets, so we can use friendlier wording."""
        return self.entity_column.lower() == "planet"

    def _entity_noun(self):
        """Plural word for the records, used in filter answers."""
        if self._is_planet_data():
            return "planets"
        if normalise(self.entity_column) in ("name", "entity"):
            return "records"
        return normalise(self.entity_column) + "s"

    def _bfs_path(self, start, goal):
        """Find a shortest directed path through the ordering graph."""
        start, goal = start.lower(), goal.lower()
        queue = deque([(start, [start])])
        visited = {start}

        while queue:
            node, path = queue.popleft()
            if node == goal:
                return path
            for neighbour in self.graph[node]:
                if neighbour not in visited:
                    visited.add(neighbour)
                    queue.append((neighbour, path + [neighbour]))
        return None

    def _format_attribute(self, field, value):
        """Format an attribute answer using the CSV field name and units."""
        label = field.replace("_", " ")
        unit = ""
        if "_" in field:
            suffix = field.rsplit("_", 1)[1].lower()
            if suffix in {"km", "au", "m", "kg"}:
                unit = suffix.upper() if suffix == "au" else suffix
                label = field.rsplit("_", 1)[0].replace("_", " ")
        # Friendlier wording, only when the CSV is about planets.
        if self._is_planet_data():
            if field.lower() == "class":
                label = "planetary class"
            elif field.lower() == "order":
                label = "order from the Sun"
            elif field.lower() == "distance_au":
                label = "average distance from the Sun"
            elif field.lower() == "diameter_km":
                label = "diameter"

        return label, unit

    def answer_question(self, question):
        """Answer one question and return the answer, explanation, type, and time."""
        start_time = time.perf_counter()
        q = question.strip().lower()
        mentioned = self._find_entities(q)           # may contain repeats
        entity = mentioned[0] if mentioned else None
        result, trace, question_type = None, [], "unmatched"

        # Template 1: Attribute lookup, e.g. "What is the diameter of Earth?"
        # Also handles several attributes or several entities in one question.
        if entity and any(term in q for term in ("what", "tell me")):
            fields = self._find_attributes(q)
            if fields:
                sentences = []
                for name in dict.fromkeys(mentioned):    # unique, keeps order
                    for field in fields:
                        value = self.records[name.lower()][field]
                        label, unit = self._format_attribute(field, value)
                        unit_text = (" " + unit) if unit else ""
                        sentences.append(f"{name}'s {label} is {value}{unit_text}.")
                        trace.append(f"({name}, has_{field}, {value})")
                result = " ".join(sentences)
                question_type = "simple lookup"

        # Template 2: Filter entities by a field value.
        if result is None and any(word in q for word in ("which", "list")):
            for field in self.headers:
                if field == self.entity_column:
                    continue
                matching_value = self._find_value(q, field)
                if matching_value is not None:
                    names = [
                        record["name"] for record in self.records.values()
                        if str(record[field]).lower() == matching_value
                    ]
                    result = (
                        f"The {matching_value} {self._entity_noun()} are: "
                        f"{', '.join(names)}."
                    )
                    trace = [
                        f"Filtered triples with relation has_{field} "
                        f"and object '{matching_value}'."
                    ]
                    question_type = "attribute filter"
                    break

        # Template 3: Compare order using BFS over the directed graph.
        before_words = {"closer", "nearer", "before", "earlier"}
        after_words = {"farther", "further", "after", "later"}
        q_words = set(normalise(q).split())
        if result is None and (q_words & (before_words | after_words)):
            if len(mentioned) >= 2 and self.order_column:
                first, second = mentioned[0], mentioned[1]
                asks_after = bool(q_words & after_words)

                # "A is after B" is the same as "B is before A", so the BFS
                # always searches from the earlier record to the later one.
                start, goal = (second, first) if asks_after else (first, second)

                if self._is_planet_data():
                    relation = "farther from the Sun than" if asks_after else "closer to the Sun than"
                    yes_text, no_text = f"is {relation}", f"is not {relation}"
                else:
                    relation = "after" if asks_after else "before"
                    yes_text, no_text = f"comes {relation}", f"does not come {relation}"

                if first.lower() == second.lower():
                    result = f"No. {first} {no_text} itself."
                    trace = [f"Both names refer to the same record: {first}."]
                else:
                    path = self._bfs_path(start, goal)
                    if path is not None:
                        result = f"Yes. {first} {yes_text} {second}."
                        trace = [
                            "BFS path: " + " -> ".join(name.title() for name in path)
                        ]
                    else:
                        result = f"No. {first} {no_text} {second}."
                        trace = [
                            f"No directed path from {start} to {goal} "
                            "in the ordering graph."
                        ]
                question_type = "multi-step reasoning"

        # Template 4: Yes/no check for an entity and a categorical CSV value.
        if result is None and entity and re.search(r"\b(is|are)\b", q):
            for field in self.headers:
                if field == self.entity_column:
                    continue
                # Match the value asked about, then compare it with the stored value.
                asked_value = self._find_value(q, field)
                if asked_value is not None:
                    stored_value = self.records[entity.lower()][field]
                    is_match = str(stored_value).lower() == asked_value
                    label, unit = self._format_attribute(field, stored_value)
                    unit_text = (" " + unit) if unit else ""
                    if is_match:
                        result = f"Yes. {entity}'s {label} is {stored_value}{unit_text}."
                    else:
                        result = (
                            f"No. {entity}'s {label} is {stored_value}{unit_text}, "
                            f"not {asked_value}."
                        )
                    trace = [
                        f"({entity}, has_{field}, {stored_value})"
                    ]
                    question_type = "yes/no lookup"
                    break

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        if result is None:
            result = "Not found in the document."
            trace = ["No supported question template or matching fact was found."]
            question_type = "not found"

        return {
            "question": question,
            "answer": result,
            "trace": trace,
            "type": question_type,
            "time_ms": round(elapsed_ms, 4),
        }


def main():
    """Run the command-line version of the document QA system."""
    default_file = Path(__file__).with_name("sample_data") / "planets.csv"
    file_name = input(
        f"Enter CSV file path (press Enter for {default_file.name}): "
    ).strip()
    csv_path = Path(file_name) if file_name else default_file

    try:
        agent = DocumentQASystem(csv_path)
    except (OSError, ValueError) as error:
        print("Could not build the knowledge base:", error)
        return

    print("\nDOCUMENT QUESTION ANSWERING SYSTEM")
    print(
        f"Knowledge base loaded: {len(agent.records)} records, "
        f"{len(agent.triples)} triples"
    )
    print("Templates: attribute lookup | attribute filter | closer-than | yes/no")
    print("Type 'exit' to stop.")

    while True:
        question = input("\nAsk a question: ").strip()
        if question.lower() == "exit":
            break
        response = agent.answer_question(question)
        print("Answer:", response["answer"])
        print("Explanation trace:")
        for item in response["trace"]:
            print(" -", item)
        print(f"Response time: {response['time_ms']} ms")


if __name__ == "__main__":
    main()
