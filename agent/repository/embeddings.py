from langchain_google_genai import GoogleGenerativeAIEmbeddings
from dotenv import load_dotenv
load_dotenv()


embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001",)

def embed_text(text: str) -> list[float]:
    return embeddings.embed_query(text)