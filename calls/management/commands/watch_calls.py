import os
import time
import datetime
from django.core.management.base import BaseCommand
from django.utils.timezone import make_aware
from django.conf import settings
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from calls.models import Call, User

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
            self.process_file(event.src_path, is_conversation=False)
        elif filename.endswith('_full_conversation.wav'):
            self.stdout.write(f"Detected conversation file: {filename}")
            self.process_file(event.src_path, is_conversation=True)

    def process_file(self, wav_path, is_conversation=False):
        # Wait a brief moment to ensure file write is complete (optional but safer)
        time.sleep(1)

        try:
            # Path structure: .../caller_id/filename.wav
            dir_path = os.path.dirname(wav_path)
            caller_id = os.path.basename(dir_path)
            filename = os.path.basename(wav_path)

            # Extract Session ID
            if is_conversation:
                 # format: {caller_id}_{session_id}_full_conversation.wav
                 base_name = filename.replace('_full_conversation.wav', '')
            else:
                 # format: {caller_id}_{session_id}_full.wav
                 base_name = filename.replace('_full.wav', '')
            
            parts = base_name.split('_')
            # Assuming format is always caller_id_sessionid...
            # If caller_id can contain underscores, this might be tricky. 
            # But based on user script: session_id=$(echo "$base_name" | cut -d'_' -f2)
            # which implies caller_id is the first part.
            session_id = parts[1] if len(parts) >= 2 else base_name

            # Check if User exists
            user = User.objects.filter(phone_number=caller_id).first()
            if not user:
                self.stdout.write(self.style.WARNING(f"Ignored file from {caller_id}: User not registered."))
                return

            relative_path = os.path.join(caller_id, filename)

            if is_conversation:
                # Update existing call with conversation file
                # We use update_or_create just in case the conversation file comes BEFORE the full.wav (rare but possible)
                # If call exists, update full_conversation_filename.
                # If not, create it with just this field (and other defaults)
                call, created = Call.objects.update_or_create(
                    session_id=session_id,
                    defaults={
                        'user': user,
                        'caller_id': caller_id,
                        'full_conversation_filename': relative_path,
                        # We don't overwrite other fields if they exist, but if creating, we need defaults
                        # We might need to leave other fields blank if creating from conversation file first
                    }
                )
                if created:
                     self.stdout.write(self.style.SUCCESS(f"Created partial call record for {session_id} (conversation file first)"))
                else:
                     self.stdout.write(self.style.SUCCESS(f"Updated call {session_id} with conversation file"))
                return

            # Normal _full.wav processing
            txt_filename = filename.replace('_full.wav', '_full.txt')
            txt_path = os.path.join(dir_path, txt_filename)

            # Check if conversation file ALREADY exists in this folder (in case we missed the event or doing initial scan)
            conversation_filename = filename.replace('_full.wav', '_full_conversation.wav')
            conversation_path = os.path.join(dir_path, conversation_filename)
            full_conv_relative = None
            if os.path.exists(conversation_path):
                full_conv_relative = os.path.join(caller_id, conversation_filename)

            # Metadata
            wav_size = os.path.getsize(wav_path)
            created_timestamp = os.path.getmtime(wav_path)
            created_at = make_aware(datetime.datetime.fromtimestamp(created_timestamp))

            txt_size = 0
            transfer_reasons = ""
            transfer_reason_descriptions = ""

            if os.path.exists(txt_path):
                txt_size = os.path.getsize(txt_path)
                try:
                    with open(txt_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                        for line in content.splitlines():
                            if line.startswith('TRANSFER_REASONS:'):
                                transfer_reasons = line.replace('TRANSFER_REASONS:', '').strip()
                            if line.startswith('TRANSFER_REASON_DESCRIPTIONS:'):
                                transfer_reason_descriptions = line.replace('TRANSFER_REASON_DESCRIPTIONS:', '').strip()
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"Error reading txt file: {e}"))

            # Prepare defaults
            defaults = {
                'user': user,
                'caller_id': caller_id,
                'wav_filename': relative_path,
                'txt_filename': txt_filename,
                'wav_size': wav_size,
                'txt_size': txt_size,
                'created_at': created_at,
                'transfer_reasons': transfer_reasons,
                'transfer_reason_descriptions': transfer_reason_descriptions,
            }
            # Only update full_conversation_filename if we found it, otherwise don't overwrite it (if it was set by the other event)
            if full_conv_relative:
                defaults['full_conversation_filename'] = full_conv_relative

            Call.objects.update_or_create(
                session_id=session_id,
                defaults=defaults
            )
            self.stdout.write(self.style.SUCCESS(f"Processed match call {session_id}"))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error processing file {wav_path}: {e}"))


class Command(BaseCommand):
    help = 'Watches for new call recordings and processes them in real-time'

    def add_arguments(self, parser):
        parser.add_argument('--path', type=str, default='/usr/local/share/asterisk/sounds/call_sessions', help='Path to watch')

    def handle(self, *args, **options):
        path = options['path']
        if not os.path.exists(path):
            self.stdout.write(self.style.WARNING(f"Path {path} does not exist. Waiting..."))
            
        # Initial Scan
        self.stdout.write(f"Performing initial scan of {path}...")
        handler = CallHandler(self.stdout, self.style)
        for root, dirs, files in os.walk(path):
            for file in files:
                if file.endswith('_full.wav'):
                    handler.process_file(os.path.join(root, file), is_conversation=False)
                elif file.endswith('_full_conversation.wav'):
                     handler.process_file(os.path.join(root, file), is_conversation=True)
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
