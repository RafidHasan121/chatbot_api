from django.http import StreamingHttpResponse
from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view
import os
from .services import *
from openai import OpenAI

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
            return Response ("PROVIDE APPROPRIATE KEYS", status=400)

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
        return thread_id
        """

        message = request.data.get("message")
        project = request.data.get("project")
        t_id = request.data.get("thread_id")

        client = OpenAI(api_key=os.environ.get("API_KEY"))

        # previous thread

        if t_id:
            message = continue_run_request(client, project, message, t_id)

        # new thread

        else:
            message = new_run_request(client, message, project)
            

        return Response({
            "thread_id": message.thread_id,
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


@api_view(['GET'])
def get_chat_history(request):
    thread_id = request.query_params.get('thread_id')
    page = request.query_params.get('page_number') or 0
    limit = request.query_params.get('chat_limit') or 5
    supabase = init_supabase()
    page = int(page)
    limit = int(limit)
    data, error = supabase.table('chat_history').select('*').eq('thread_id', thread_id).order('created_at', desc=True).limit(limit).offset(page*limit).execute()
    return Response(data[1])


@api_view(['POST'])
def upload_chat_history(request):
    role = request.data.get("role")     # "user"/"gpt"
    project_id = request.data.get("project_id")
    thread_id = request.data.get("thread_id")
    message = request.data.get("message")
    insert_chat_history(project_id, thread_id, message, role)
    return Response({"status" : "completed"},status=200) 

@api_view(['POST'])
def upload_group_thread(request):
    project = request.data.get("project_id")
    member = request.data.get("member_id")
    insert_group_thread(project, member)
    return Response({"status" : "completed"},status=200)

@api_view(['GET'])
def get_thread_id(request):
    id = request.query_params.get('id')
    supabase = init_supabase()
    response = supabase.table('chat_history').select(
        "thread_id", count='exact').eq('project_id', id).execute()
    return Response(response)