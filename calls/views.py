from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.views.generic import CreateView, ListView, View
from django.contrib.auth.views import LoginView
from django.urls import reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, Http404, FileResponse
from django.conf import settings
import os
import mimetypes

from .forms import CustomUserCreationForm
from .models import Call

class SignupView(CreateView):
    form_class = CustomUserCreationForm
    success_url = reverse_lazy('login')
    template_name = 'calls/signup.html'

class CustomLoginView(LoginView):
    template_name = 'registration/login.html'

class DashboardView(LoginRequiredMixin, ListView):
    model = Call
    template_name = 'calls/dashboard.html'
    context_object_name = 'calls'
    paginate_by = 20
    ordering = ['-created_at']

    def get_queryset(self):
        # Admin sees all calls, regular user sees only their own
        if self.request.user.is_staff:
             queryset = Call.objects.all()
        else:
             queryset = Call.objects.filter(user=self.request.user)
        
        # Search filtering
        search_query = self.request.GET.get('q')
        if search_query:
            from django.db.models import Q
            queryset = queryset.filter(
                Q(caller_id__icontains=search_query) | 
                Q(session_id__icontains=search_query)
            )
            
        return queryset.order_by('-created_at')

class PlayAudioView(LoginRequiredMixin, View):
    def get(self, request, pk):
        try:
            if request.user.is_staff:
                call = Call.objects.get(pk=pk)
            else:
                call = Call.objects.get(pk=pk, user=request.user)
        except Call.DoesNotExist:
            raise Http404("Call not found")

        # Check file type requested
        file_type = request.GET.get('type', 'filtered') # 'filtered' (default) or 'conversation'
        
        recordings_root = getattr(settings, 'RECORDINGS_ROOT', '/usr/local/share/asterisk/sounds/call_sessions')
        
        if file_type == 'conversation':
            if not call.full_conversation_filename:
                 raise Http404("Conversation file not available")
            file_path = os.path.join(recordings_root, call.full_conversation_filename)
        else:
            file_path = os.path.join(recordings_root, call.wav_filename)
            
        # Resolve any .. components to get absolute path and ensure it's safe
        file_path = os.path.abspath(file_path)
        
        if not os.path.exists(file_path):
             raise Http404("Audio file not found on server")

        # Secure file serving
        # For development, FileResponse is fine. For production, X-Sendfile / X-Accel-Redirect is better.
        
        # Check if download requested
        download = request.GET.get('download') == 'true'
        
        content_type, encoding = mimetypes.guess_type(file_path)
        content_type = content_type or 'application/octet-stream'

        response = FileResponse(open(file_path, 'rb'), content_type=content_type)
        if download:
            response['Content-Disposition'] = f'attachment; filename="{os.path.basename(file_path)}"'
        else:
            response['Content-Disposition'] = f'inline; filename="{os.path.basename(file_path)}"'
            
        return response
