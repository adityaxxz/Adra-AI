embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001",output_dimensionality=768)

### TODO ✅
- delete feature in new project generation
- generate again button, to regenerate the project if error happens with the llm like resourse exhaustion, so that user dont need to create the same project again and again
- fix the need to reload the page to see the changes


### TODO 🔜
- fix the edit files response, and make it more efficient
- improve the code aware chunking strategy