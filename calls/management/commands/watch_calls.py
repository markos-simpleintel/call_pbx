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
            self.process_file(event.src_path)

    def process_file(self, wav_path):
        # Wait a brief moment to ensure file write is complete (optional but safer)
        time.sleep(1)

        try:
            # Path structure: .../caller_id/filename.wav
            dir_path = os.path.dirname(wav_path)
            caller_id = os.path.basename(dir_path)
            filename = os.path.basename(wav_path)

            # Extract Session ID
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

            # Normal _full.wav processing
            txt_filename = filename.replace('_full.wav', '_full.txt')
            txt_path = os.path.join(dir_path, txt_filename)

            # Check for conversation file in sibling directory: ../{caller_session}/full_conversation.wav
            # dir_path is likely .../call_sessions/{caller_id}
            # We need .../sounds/{caller_session}/full_conversation.wav
            # which is ../../{caller_session}/full_conversation.wav relative to dir_path
            # OR ../{caller_session}/full_conversation.wav relative to root (call_sessions)
            
            # Construct the absolute path to check
            # We assume dir_path is .../call_sessions/{caller_id}
            # so dir_path/../../ is .../sounds/
            sounds_root = os.path.abspath(os.path.join(dir_path, '../../')) 
            conversation_dir = os.path.join(sounds_root, base_name) # base_name is {caller_id}_{session_id}
            conversation_file_path = os.path.join(conversation_dir, 'full_conversation.wav')
            
            full_conv_relative = None
            if os.path.exists(conversation_file_path):
                # Store relative to call_sessions (which is the settings.RECORDINGS_ROOT)
                # So path should be ../{base_name}/full_conversation.wav
                full_conv_relative = os.path.join('..', base_name, 'full_conversation.wav')
                self.stdout.write(f"Found conversation file at {full_conv_relative}")

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
                    handler.process_file(os.path.join(root, file))
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
