from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GeneratedDraft:
    kind: str
    title: str
    instructions: str
    marks: int | None = None


class ContentGenerator:
    def generate(self, kind: str, topic: str, marks: int | None = None) -> GeneratedDraft:
        cleaned_topic = topic.strip() or "Class Topic"
        if kind == "quiz":
            return self._quiz(cleaned_topic, marks)
        if kind == "rubric":
            return self._rubric(cleaned_topic, marks)
        return self._assignment(cleaned_topic, marks)

    def _assignment(self, topic: str, marks: int | None) -> GeneratedDraft:
        points = marks or 20
        instructions = (
            f"Complete the following assignment on {topic}.\n\n"
            "Tasks:\n"
            "1. Write a short explanation of the main concept.\n"
            "2. Give two real-world examples.\n"
            "3. Solve or answer the practice questions shared in class.\n"
            "4. Submit your work clearly with your name and roll number.\n\n"
            "Evaluation:\n"
            "- Concept understanding: 40%\n"
            "- Completeness: 30%\n"
            "- Examples and explanation quality: 20%\n"
            "- Presentation: 10%"
        )
        return GeneratedDraft(
            kind="assignment",
            title=f"{topic} Assignment",
            instructions=instructions,
            marks=points,
        )

    def _quiz(self, topic: str, marks: int | None) -> GeneratedDraft:
        points = marks or 10
        instructions = (
            f"Quiz: {topic}\n\n"
            "Questions:\n"
            "1. Define the key idea in your own words.\n"
            "2. List two important characteristics.\n"
            "3. Explain one practical example.\n"
            "4. Differentiate it from a related concept.\n"
            "5. Write one short note on why it is important.\n\n"
            "Answer all questions briefly and clearly."
        )
        return GeneratedDraft(
            kind="quiz",
            title=f"{topic} Quiz",
            instructions=instructions,
            marks=points,
        )

    def _rubric(self, topic: str, marks: int | None) -> GeneratedDraft:
        points = marks or 20
        instructions = (
            f"Rubric for {topic}\n\n"
            "Criteria:\n"
            f"- Accuracy and concept understanding: {round(points * 0.4)} marks\n"
            f"- Completeness of required work: {round(points * 0.25)} marks\n"
            f"- Examples, reasoning, and explanation quality: {round(points * 0.2)} marks\n"
            f"- Formatting and timely submission: {points - round(points * 0.4) - round(points * 0.25) - round(points * 0.2)} marks\n\n"
            "Use this rubric to grade the submitted work consistently."
        )
        return GeneratedDraft(
            kind="rubric",
            title=f"{topic} Rubric",
            instructions=instructions,
            marks=points,
        )
