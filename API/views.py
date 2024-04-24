from io import BytesIO, StringIO
import json
import time
from django.http import StreamingHttpResponse
from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view
import os
import tiktoken
from supabase import create_client, Client
from openai import OpenAI
# create functions here


def json_uploader(client, project_id):
    from timeit import default_timer as timer
    start = timer()

    supabase = init_supabase()
    routes = get_routes(supabase, project_id)

    check1 = timer()

    # convert json data
    routes_json = json.dumps(routes.data[0].get('routes'))

    check2 = timer()

    # creating chunks
    file_list = create_chunks(routes_json)

    check3 = timer()

    # counting each chunk token size
    # for each in file_list:
    #     print(count_tokens(each))

    # create files in openai
    id_list = []
    for i, chunk in enumerate(file_list):
        in_memory_file = StringIO()
        in_memory_file.write(chunk)
        encoded_bytes = in_memory_file.getvalue().encode('utf-8')
        bytes_io = BytesIO(encoded_bytes)
        bytes_io.name = f'project_id-{project_id}_chunk{i+1}.txt'
        file_object = client.files.create(
            file=bytes_io,
            purpose="assistants"
        )
        id_list.append(file_object.id)

    check4 = timer()

    print("getting routes: " + str(check1-start))
    print("converting json: " + str(check2-check1))
    print("creating chunks: " + str(check3-check2))
    print("uploading files: " + str(check4-check3))
    return id_list


def streaming_generator(run):
    for chunk in run:
        if chunk.event == "thread.message.delta":
            print(chunk.data)
            yield chunk.data.delta.content[0].text.value


def count_tokens(filename: str, model_name="gpt-4-turbo") -> int:
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


def create_chunks(the_file, model_name="gpt-4-turbo", max_tokens_per_chunk=125000):
    # Initialize the tokenizer
    tokenizer = tiktoken.encoding_for_model(model_name)

    # Encode the text_data into token integers
    token_integers = tokenizer.encode(the_file)

    # Split the token integers into chunks based on max_tokens
    chunks = [
        token_integers[i: i + max_tokens_per_chunk]
        for i in range(0, len(token_integers), max_tokens_per_chunk)
    ]

    # Decode token chunks back to strings
    chunks = [tokenizer.decode(chunk) for chunk in chunks]
    return chunks


def init_supabase(url: str = os.environ.get("SUPABASE_URL"), key: str = os.environ.get("SUPABASE_KEY")):
    supabase: Client = create_client(url, key)
    return supabase


def get_projects(supabase):
    response = supabase.table('projects').select(
        "name", "id", count='exact').execute()
    return response


def get_routes(supabase, project_id):
    response = supabase.table('projects').select(
        "routes").eq('id', project_id).execute()
    return response


def insert_chat_history(project_id, thread_id, message_id, message):
    supabase = init_supabase()
    data, count = supabase.table('chat_history').insert({
        "project_id": project_id,
        "thread_id": thread_id,
        "message_id": message_id,
        "message": message
    }).execute()
    return data


def continue_run_request(client, project, msg, t_id):
    thread_message = client.beta.threads.messages.create(
        t_id,
        role="user",
        content=msg,
    )

    insert_chat_history(project_id=project, thread_id=t_id,
                        message_id=thread_message.id, message=msg)

    return thread_message


def new_run_request(client, msg, project_id):
    from timeit import default_timer as timer

    id_list = json_uploader(client, project_id)

    start = timer()

    # creating empty thread and message

    empty_thread = client.beta.threads.create()

    thread_message = client.beta.threads.messages.create(
        empty_thread.id,
        role="user",
        content=msg,
        file_ids = id_list
    )

    # creating chat history entry

    insert_chat_history(project_id=project_id,
                        thread_id=thread_message.thread_id,
                        message_id=thread_message.id,
                        message=msg)

    check5 = timer()

    print("inserting chat history: " + str(check5-start))

    return thread_message


def the_run(client, thread_id):
    # creating run
    try:

        run = client.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=os.environ.get("ASSISTANT_ID"),
            stream=True
        )

    except:
        return False

    return run


def get_request(client, run_id, thread_id):
    """
    The sync get request. Currently unused
    """

    run = client.beta.threads.runs.retrieve(
        thread_id=thread_id,
        run_id=run_id
    )

    if run.status == 'completed':
        # getting the thread messages list
        thread_messages = client.beta.threads.messages.list(thread_id)
        result = thread_messages.data[0].content[0].text.value
        # result = thread_messages
        return result
    else:
        return False


# Create your views here.

class assistant(APIView):
    auth_headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + os.environ.get("API_KEY"),
        "OpenAI-Beta": "assistants=v1"
    }

    # def get(self, request, *args, **kwargs):

    #     client = OpenAI(api_key=os.environ.get("API_KEY"))
    #     run = request.query_params.get("run_id")
    #     thread = request.query_params.get("thread_id")
    #     response_message = get_request(client, run, thread)
    #     if response_message == False:
    #         return Response("generating", status=201)
    #     return Response(response_message)


    def get(self, request, *args, **kwargs):
        """
        request = get
        thread_id = text # thread_id
        return streamResponse
        """
        
        client = OpenAI(api_key=os.environ.get("API_KEY"))
        thread = request.query_params.get("thread_id")
        try:
            run = client.beta.threads.runs.create(
            thread_id=thread,
            assistant_id=os.environ.get("ASSISTANT_ID"),
            stream=True
        )
        except:
            return False

        if run == False:
                return Response("Error while running", status=400)

        # async response

        response = StreamingHttpResponse(
            streaming_generator(run), status=200, content_type='text/event-stream')
        return response

        # sync response

        # return Response({
        #     "run_id" : run.id,
        #     "thread_id" : run.thread_id})
    
    def post(self, request, *args, **kwargs):
        """
        request = post
        message = text #the_query
        project = intfield #project_id
        t_id = text #thread_id optional if continuation
        return thread_id, message_id
        """

        message = request.data.get("message")
        project = request.data.get("project")
        t_id = request.data.get("t_id")

        client = OpenAI(api_key=os.environ.get("API_KEY"))

        # previous thread

        if t_id:
            run = continue_run_request(client, project, message, t_id)

        # new thread

        else:
            run = new_run_request(client, message, project)

        return Response({
            "thread_id": run.thread_id,
            "message_id": run.id
        })

    def patch(self, request, *args, **kwargs):
        project_id = request.data.get("project")
        t_id = request.data.get("t_id")
        client = OpenAI(api_key=os.environ.get("API_KEY"))

        supabase = init_supabase()
        json_data = get_routes(supabase, project_id)
        id_list = json_uploader(client, project_id)

        client.beta.threads.messages.create(
            thread_id=t_id, role="user",
            content="the updated json for the project has been attached to this message, future queries are based on this JSON",
            file_ids=id_list)

        run = client.beta.threads.runs.create(
            thread_id=t_id,
            assistant_id=os.environ.get("ASSISTANT_ID"),
        )

        return Response({"result": "JSON updated"}, status=200)


@api_view(['GET'])
def project_list(request):
    """
    GET all project list here

    """
    client = init_supabase()
    project_list = get_projects(client)
    return Response(project_list.data)


@api_view(['POST'])
def supabase_test(request):
    project_id = request.data.get("project")
    thread_id = request.data.get("thread")
    message_id = request.data.get("message")
    message = request.data.get("the_message")
    data = insert_chat_history(project_id, thread_id, message_id, message)
    return Response(data, status=200)
