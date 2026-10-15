"""The preview graph's link cleaning: only links between known concepts, no self-links or duplicates, no
unknown types, and never a prerequisite loop (a loop would send practice round in circles)."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "build_concept_graph_preview", Path(__file__).resolve().parents[1] / "scripts" / "build_concept_graph_preview.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_names_become_kebab_case():
    assert mod.slug("Call Stack") == "call-stack"
    assert mod.slug("  useMemo() hook ") == "usememo-hook"


def test_links_are_cleaned_and_prerequisite_loops_dropped():
    names = {"call-stack", "event-loop", "microtask-queue", "promises"}
    rels = [
        {"source": "Call Stack", "target": "event-loop", "type": "prerequisite_of"},
        {"source": "event-loop", "target": "microtask-queue", "type": "prerequisite_of"},
        {"source": "microtask-queue", "target": "call-stack", "type": "prerequisite_of"},   # would close a loop
        {"source": "event-loop", "target": "event-loop", "type": "related_to"},             # self-link
        {"source": "event-loop", "target": "generators", "type": "related_to"},             # unknown concept
        {"source": "promises", "target": "microtask-queue", "type": "depends_on"},           # unknown type
        {"source": "promises", "target": "microtask-queue", "type": "related_to"},
        {"source": "microtask-queue", "target": "promises", "type": "related_to"},          # same link reversed
    ]
    assert mod.clean_relationships(rels, names) == [
        {"source": "call-stack", "target": "event-loop", "type": "prerequisite_of"},
        {"source": "event-loop", "target": "microtask-queue", "type": "prerequisite_of"},
        {"source": "promises", "target": "microtask-queue", "type": "related_to"},
    ]
