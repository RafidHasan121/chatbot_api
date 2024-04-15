from io import BytesIO, StringIO
import json
import time
from django.shortcuts import render
from rest_framework.views import APIView 
from rest_framework.response import Response
import os 
import tiktoken
from supabase import create_client, Client
from openai import OpenAI
#create functions here

def count_tokens(filename: str, model_name="gpt-4") -> int:
    """Count the number of tokens in a file using TikToken."""
    try:
        with open(filename, 'r') as file:
            content = file.read()
            # Get the tokenizer encoding for the specified model
            encoding = tiktoken.encoding_for_model(model_name)
            tokens = encoding.encode(content)
            return len(tokens)
    except FileNotFoundError:
        print("File not found.")
        return 0

def create_chunks(the_file, model_name="gpt-4-turbo-preview", max_tokens_per_chunk=125000):
    # Get the tokenizer encoding for the specified model
    encoding = tiktoken.encoding_for_model(model_name)

    # Divide the text into chunks based on tokens
    chunks = []
    current_chunk = ""
    current_token_count = 0

    for line in the_file.split('\n'):
        line_tokens = encoding.encode(line)
        line_token_count = len(line_tokens)

        if current_token_count + line_token_count > max_tokens_per_chunk:
            chunks.append(current_chunk)
            current_chunk = line + '\n'
            current_token_count = line_token_count
        else:
            current_chunk += line + '\n'
            current_token_count += line_token_count

    if current_chunk:
        chunks.append(current_chunk)
    
    return chunks

def init_supabase(url: str = os.environ.get("SUPABASE_URL"), key: str = os.environ.get("SUPABASE_KEY")):
    supabase: Client = create_client(url, key)
    return supabase

def get_projects(supabase):
    response = supabase.table('projects').select(
        "name", count='exact').execute()
    return response

def get_routes(supabase, project_name):
    response = supabase.table('projects').select(
        "routes").eq('name', project_name).execute()
    return response

def continue_run_request(client, msg, t_id):
    thread_message = client.beta.threads.messages.create(
        t_id,
        role="user",
        content=msg,
    )
    run = client.beta.threads.runs.create(
        thread_id=t_id,
        assistant_id=os.environ.get("ASSISTANT_ID")
    )
    return run

def new_run_request(client, msg, project_name):
    supabase = init_supabase()
    routes = get_routes(supabase, project_name)
    
    # convert json data
    routes_json = json.dumps(routes.data[0].get('routes'))
    
    # creating chunks
    file_list = create_chunks(routes_json)
    
    #counting each chunk token size
    # for each in file_list:
    #     print(count_tokens(each))
    
    # create files in openai
    id_list = []
    for i, chunk in enumerate(file_list):
        in_memory_file = StringIO()
        in_memory_file.write(chunk)
        encoded_bytes = in_memory_file.getvalue().encode('utf-8')
        bytes_io = BytesIO(encoded_bytes)
        bytes_io.name = f'chunk{i+1}.txt' 
        file_object = client.files.create(
            file=bytes_io,
            purpose="assistants"
        )
        id_list.append(file_object.id)
        print(file_object)
    
    # create run 
    run = client.beta.threads.create_and_run(
        assistant_id= os.environ.get("ASSISTANT_ID"),
        thread={
            "messages": [
                {"role": "user", "content": "The file attached is a .txt file which has a json in it, do the following for the json" + "\n" + msg, "file_ids": id_list}
            ]
        }
    )
    return run

def get_request(client, run):

    # checking run status until completed
    while True:
        run = client.beta.threads.runs.retrieve(
            thread_id=run.thread_id,
            run_id=run.id
        )
        if run.status == 'completed':
            break
        time.sleep(1)  # Wait for five second before checking again

    # getting the thread messages list
    thread_messages = client.beta.threads.messages.list(run.thread_id)
    result = thread_messages.data[0].content[0].text.value
    return result

# Create your views here.

class assistant(APIView):
   auth_headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + os.environ.get("API_KEY"),
        "OpenAI-Beta": "assistants=v1"
    }
   
   def get(self, request, *args, **kwargs):
        """
        GET all project list here
    
        """
        client = init_supabase()
        project_list = get_projects(client)
        return Response(project_list.data)
   
   def post(self, request, *args, **kwargs):
        """
        message = charfield #the_query
        project = charfield #project_name

        return generated response
        """
        
        message = request.data.get("message")
        project = request.data.get("project")
        try:
            t_id = request.session['thread_id']
        except:
            t_id = None

        client = OpenAI(api_key=os.environ.get("API_KEY"))
        
        # previous thread 
        # it doesn't work now
        if t_id:
            run = continue_run_request(client, message, t_id)
            print(t_id)

        # new thread
        # this is what works
        else:
            run = new_run_request(client, message, project)

        response_message = get_request(client, run)
        return Response(response_message)
   