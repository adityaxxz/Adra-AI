embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001",output_dimensionality=768)

### TODO ✅
- delete feature in new project generation
- generate again button, to regenerate the project if error happens with the llm like resourse exhaustion, so that user dont need to create the same project again and again
- fix the need to reload the page to see the changes


### TODO 🔜
- fix the edit files response, and make it more efficient
- improve the code aware chunking strategy for py files

- when uploading folder from local, it use the folder name rather than the provided name, fix it 

- the code editor isnt working, the graph workflow is working correctly but the edited files from the repo isnt showing on the site, i want when i give it a prompt to edit something from a file it shows "edited files: file_name" and automatically loads the site with the new edited file above, right now th chat just shows ... 
