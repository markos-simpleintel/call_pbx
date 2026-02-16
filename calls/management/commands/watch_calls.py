import os
import time
import datetime
from django.core.management.base import BaseCommand
from django.utils.timezone import make_aware
from django.conf import settings
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from calls.models import Call, User

from calls.utils import process_call_file

class CallHandler(FileSystemEventHandler):
    def __init__(self, stdout, style):
        self.stdout = stdout
        self.style = style

    def on_created(self, event):
        if event.is_directory:
            return
        
        filename = os.path.basename(event.src_path)
        if filename.endswith('_full.wav'):
            self.stdout.write(f"Detected new call: {filename}")
            self.process_file(event.src_path)

    def process_file(self, wav_path):
        # Wait a brief moment to ensure file write is complete (optional but safer)
        time.sleep(1)
        # Use valid utility function
        process_call_file(wav_path, self.stdout, self.style)


class Command(BaseCommand):
    help = 'Watches for new call recordings and processes them in real-time'

    def add_arguments(self, parser):
        parser.add_argument('--path', type=str, default='/usr/local/share/asterisk/sounds/call_sessions', help='Path to watch')

    def handle(self, *args, **options):
        path = options['path']
        if not os.path.exists(path):
            self.stdout.write(self.style.WARNING(f"Path {path} does not exist. Waiting..."))
            
        # Initial Scan (Optimized for performance)
        self.stdout.write(f"Performing initial scan of {path} for registered users...")
        handler = CallHandler(self.stdout, self.style)
        
        # Only scan folders of registered users
        registered_numbers = User.objects.values_list('phone_number', flat=True)
        
        for phone_number in registered_numbers:
            user_dir = os.path.join(path, phone_number)
            if os.path.exists(user_dir):
                # self.stdout.write(f"Scanning calls for {phone_number}...")
                for root, dirs, files in os.walk(user_dir):
                    for file in files:
                        if file.endswith('_full.wav'):
                            handler.process_file(os.path.join(root, file))
            else:
                # User might not have any calls folder yet
                pass
                
        self.stdout.write(self.style.SUCCESS("Initial scan complete."))

        self.stdout.write(f"Starting watchdog on {path}...")
        
        # We use the native Observer (Inotify on Linux) for efficient event sensing
        observer = Observer()
        observer.schedule(handler, path, recursive=True)
        observer.start()

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()
