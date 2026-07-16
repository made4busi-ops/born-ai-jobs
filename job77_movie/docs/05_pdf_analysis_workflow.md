# Job 77 – PDF Analysis & Script Generation Workflow

## Steps

1. **Upload PDF**  
   User uploads a PDF or document.

2. **Extract Text**  
   Pull all text from the PDF (using pypdf or similar).

3. **AI Analysis**  
   Send content to Gemini or Grok to:
   - Summarize the document
   - Identify main topics/chapters
   - Suggest movie structure

4. **Script Generation**  
   Generate a clean script with:
   - Scene descriptions
   - Narration/dialogue
   - Timing suggestions

5. **Save to Project**  
   Store the script and analysis in the database linked to the project.

## Current Status (Simple Version)
For now we can do basic text extraction + call an AI model for script generation.
Later we can make it more advanced.
