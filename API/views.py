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


@api_view(['GET'])
def get_chat_history(request):
    thread_id = request.query_params.get('thread')
    page : int = request.query_params.get('page') or 0
    limit : int = request.query_params.get('limit') or 5
    supabase = init_supabase()
    data, error = supabase.table('chat_history').select('*').eq('thread_id', thread_id).order('created_at', desc=True).limit(limit).offset(page*limit).execute()
    return Response(data[1])
