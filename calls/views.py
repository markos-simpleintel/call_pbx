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
        # Filter calls by the logged-in user
        return Call.objects.filter(user=self.request.user).order_by('-created_at')

class PlayAudioView(LoginRequiredMixin, View):
    def get(self, request, pk):
        try:
            call = Call.objects.get(pk=pk, user=request.user)
        except Call.DoesNotExist:
            raise Http404("Call not found")

        # The path stored in wav_filename might be just the filename or full path
        # The management command stores os.path.join(root, file) which is absolute path
        # The path stored in wav_filename is relative: caller_id/filename.wav
        # We need to join it with the base recordings directory
        recordings_root = getattr(settings, 'RECORDINGS_ROOT', '/usr/local/share/asterisk/sounds/call_sessions')
        file_path = os.path.join(recordings_root, call.wav_filename)
        
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
