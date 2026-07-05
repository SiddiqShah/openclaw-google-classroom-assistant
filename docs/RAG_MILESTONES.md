# WhatsApp Classroom RAG Milestones

Project name:

```text
WhatsApp Classroom RAG + Assignment Assistant
```

Goal:

```text
Teacher uploads documents, asks questions from WhatsApp, generates quizzes/assignments from documents, reviews the AI draft, then posts approved work to Google Classroom.
```

## Milestone 1: WhatsApp RAG Bot Setup

- Use existing OpenClaw WhatsApp integration.
- Add authorized users.
- Add RAG menu:
  - Upload Document
  - Ask Question
  - List Documents

Deliverable:

```text
Teacher can send RAG commands to the existing WhatsApp bot.
```

## Milestone 2: Document Upload

- Receive PDF/DOCX/TXT from WhatsApp.
- Save file locally first.
- Optionally save file to Google Drive later.
- Validate file type and size.

Deliverable:

```text
Teacher can upload supported documents and see them in the document list.
```

## Milestone 3: Text Extraction

- Extract text from TXT.
- Extract text from PDF.
- Extract text from DOCX.
- PPTX later.
- Clean extracted text.

Deliverable:

```text
Uploaded documents can be converted into clean text.
```

## Milestone 4: Chunking

- Split text into chunks.
- Target size: 500-1000 words/tokens per chunk.
- Keep metadata:
  - file name
  - page number if available
  - class/category
  - document ID

Deliverable:

```text
Documents become searchable chunks with metadata.
```

## Milestone 5: Embeddings + Vector DB

Recommended MVP:

```text
ChromaDB
```

Production options:

```text
Qdrant
PostgreSQL pgvector
```

Deliverable:

```text
Chunks are embedded and stored in a vector database.
```

## Milestone 6: Question Answering

- Teacher asks a question on WhatsApp.
- System searches vector DB.
- Retrieves top 3-5 chunks.
- LLM answers only from document context.

Deliverable:

```text
Teacher can ask questions from uploaded documents.
```

## Milestone 7: Source References

Answer should show:

- File name
- Page number if available
- Confidence note

Example:

```text
Answer based on:
1. Biology Chapter 5.pdf, page 3
2. Biology Chapter 5.pdf, page 4
```

## Milestone 8: Admin Controls

- List uploaded documents.
- Delete document.
- Reprocess document.
- Separate knowledge bases by class/client/project.

Deliverable:

```text
Teacher/admin can manage the RAG knowledge base.
```

## Best Combined Workflow

```text
Teacher uploads chapter PDF
Teacher asks: Create 10 MCQs from this chapter for Class 9
Bot creates MCQs, answer key, title, and deadline suggestion
Teacher reviews
Teacher says: Post this as assignment in Class 9 Biology, deadline Friday 5 PM
Bot posts to Google Classroom
```

## Current Scaffold

Created package:

```text
classroom_assistant/rag_assistant
```

Created data folders:

```text
data/rag/uploads
data/rag/indexes
```

Initial modules:

```text
config.py
store.py
document_upload.py
text_extraction.py
chunking.py
qa.py
models.py
```

## Implemented In This Pass

Milestone 3:

- TXT extraction works.
- DOCX extraction works using built-in ZIP/XML parsing.
- PDF extraction path is implemented with `pypdf`; install requirements first.
- Text cleanup is included.

Milestone 4:

- Chunking works.
- Chunks are stored in SQLite with document ID, chunk index, text, and page metadata placeholder.
- Documents can be reprocessed with `rag-process`.

Milestone 5 MVP:

- ChromaDB is installed and used as the MVP vector database.
- Chunks are embedded with a deterministic local embedding function.
- SQLite keyword search remains as a fallback if ChromaDB is unavailable.
- Chroma indexes are stored next to the RAG SQLite database.

Commands:

```powershell
.\.venv\Scripts\python.exe assistant_cli.py rag-upload --phone "+923018083053" --path "C:\path\to\chapter.txt" --category "Class 9 Biology"
.\.venv\Scripts\python.exe assistant_cli.py rag-process --phone "+923018083053" --document-id 1
.\.venv\Scripts\python.exe assistant_cli.py rag-ask --phone "+923018083053" "What is photosynthesis?"
```

Production note:

- The current local embedding function is useful for a no-network MVP.
- For a client-grade version, swap it for OpenAI, Google, or another real embedding model while keeping the same ChromaDB interface.

## Implemented Final MVP Pass

Milestone 6:

- WhatsApp RAG commands are routed:
  - `RAG menu`
  - `Ask docs: your question`
  - `List documents`

Milestone 7:

- Answers include source file references.
- PDF page references are supported when `pypdf` is installed and PDFs are processed.

Milestone 8:

- Reprocess document:
  - `Reprocess document 1`
- Delete document:
  - `Delete document 1`
- CLI delete:
  - `rag-delete`

Classroom + RAG combo:

- Generate MCQs from indexed documents and prepare a Google Classroom assignment preview.
- Teacher must approve before posting.

WhatsApp examples:

```text
RAG menu
Ask docs: What is photosynthesis?
List documents
Reprocess document 1
Delete document 1
Create 10 MCQs from docs for Class 9 Biology Topic: Photosynthesis Deadline Friday 5 PM Marks 10
```

CLI examples:

```powershell
.\.venv\Scripts\python.exe assistant_cli.py rag-delete --phone "+923018083053" --document-id 1
```
