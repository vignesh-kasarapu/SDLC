---
name: ingest-crd
description: Phase 1 - ingest the client's input (one or more files or a folder - DOCX, PDF, XLSX, CSV, HTML wireframes, images, MD/TXT) into the active project with stable block IDs, analyse images with Claude vision, detect whether the input is already an FRD (intake mode), then normalise and outline it.
argument-hint: <file or folder> [more files...] [--as frd|crd]
disable-model-invocation: true
---
Ingest the client's input `$ARGUMENTS` into the active project. Follow the orchestrator rules in CLAUDE.md. `P = ../projects/<id>`.

1. **Gate.** Run `python tools/gate.py project`. Stop if it fails.
2. **Parse.** Run `python tools/parse_doc.py $ARGUMENTS`. It accepts several files and folders, and writes `01-frd/crd.md` (blocks `[C-nnn]`), `crd-index.json` and `intake.json`. Stop on error.
   - With `pdfplumber` installed, PDF tables are extracted as tables. With `pytesseract`, scanned pages are OCR'd. Otherwise scanned pages become image blocks for step 3. Mention this if the output shows scanned pages.
3. **Images (Claude vision).** If the output lists `PENDING VISUALS`:
   1. Dispatch **visual-analyst**: `PROJECT=P. Pending image blocks: <C-ids>. Write 01-frd/visuals/C-nnn.json for each.` For more than 12 images, split them over up to 3 agents in one message.
   2. Run `python tools/parse_doc.py --attach-visuals`. It must report `still pending: none`. Log the agent.
4. **Document type.** Read `P/01-frd/intake.json` and tell the user the result in one line:
   - `frd`: the client already wrote an FRD. **Intake mode**: the platform keeps the client's document and wording, extracts requirements from it, evaluates it, and asks gap questions. It does not rewrite it.
   - `crd`: raw requirements. The platform writes a full FRD from them.

   If the user disagrees, re-run step 2 with `--as frd` or `--as crd` and `--force`.
5. **Normalise.** Dispatch **doc-normalizer**: `PROJECT=P. Read 01-frd/crd.md and write 01-frd/crd-outline.md per your instructions.`
6. **Log.** Run `python tools/state.py log doc-normalizer done --detail "<counts>"`, then `python tools/state.py phase frd in_progress`.
7. **Report.** Show the user:
   - the files, the block count by kind and the document type
   - the images analysed, by kind
   - any parsing problems from `crd-outline.md`
   - the next step, `/generate-frd`

   If parsing problems affect requirement-like content (for example garbled tables), recommend fixing the source document, or providing the DOCX or the spreadsheet itself, before continuing.
