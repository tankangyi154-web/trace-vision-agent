
import os

# This public demo does not send prompts or traces to a separate observability service.
os.environ['LANGSMITH_TRACING']='false'
os.environ['LANGCHAIN_TRACING_V2']='false'
