import os
import datetime
from django.core.management.base import BaseCommand
from django.utils.timezone import make_aware
from django.db.utils import IntegrityError
from calls.models import Call, User

class Command(BaseCommand):
    help = 'Scans the recording directory and syncs calls to the database'

    def add_arguments(self, parser):
        parser.add_argument('--path', type=str, default='/usr/local/share/asterisk/sounds/call_sessions', help='Path to call sessions')

    def handle(self, *args, **options):
        base_dir = options['path']
        
        # Check if running on Windows and use a local test path if the default doesn't exist
        if os.name == 'nt' and not os.path.exists(base_dir):
             self.stdout.write(self.style.WARNING(f"Path {base_dir} not found on Windows. strictly for testing, ensuring directory exists..."))
             # For local testing on Windows, we might want to create the directory or use a relative one
             # But the script logic expects a specific structure. Let's just warn for now.
             pass

        if not os.path.exists(base_dir):
            self.stdout.write(self.style.ERROR(f"Directory {base_dir} does not exist."))
            return

        self.stdout.write(f"Scanning {base_dir}...")

        # Walk through the directory
        # logic: find *_full.wav files
        #  dir name -> caller_id
        #  filename split -> session_id
        
        count_created = 0
        count_updated = 0

        for root, dirs, files in os.walk(base_dir):
            for file in files:
                if file.endswith('_full.wav'):
                    wav_path = os.path.join(root, file)
                    dir_name = os.path.basename(root)
                    caller_id = dir_name # Folder name is caller_id
                    
                    # Filename: {caller_id}_{session_id}_full.wav or similar
                    # The user script says: base_name=$(basename "$wav_file" "_full.wav")
                    # caller_id=$(basename "$dir")
                    # session_id=$(echo "$base_name" | cut -d'_' -f2)
                    
                    base_name = file.replace('_full.wav', '')
                    parts = base_name.split('_')
                    if len(parts) >= 2:
                        session_id = parts[1]
                    else:
                        session_id = base_name # Fallback

                    txt_filename = file.replace('_full.wav', '_full.txt')
                    txt_path = os.path.join(root, txt_filename)
                    
                    try:
                        wav_stat = os.stat(wav_path)
                        wav_size = wav_stat.st_size
                        created_timestamp = wav_stat.st_mtime
                        created_at = make_aware(datetime.datetime.fromtimestamp(created_timestamp))
                    except FileNotFoundError:
                        continue

                    txt_size = 0
                    transfer_reasons = ""
                    transfer_reason_descriptions = ""

                    if os.path.exists(txt_path):
                        txt_size = os.path.getsize(txt_path)
                        with open(txt_path, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                            # Parse TRANSFER_REASONS and TRANSFER_REASON_DESCRIPTIONS
                            # Grep equivalent
                            for line in content.splitlines():
                                if line.startswith('TRANSFER_REASONS:'):
                                    transfer_reasons = line.replace('TRANSFER_REASONS:', '').strip()
                                if line.startswith('TRANSFER_REASON_DESCRIPTIONS:'):
                                    transfer_reason_descriptions = line.replace('TRANSFER_REASON_DESCRIPTIONS:', '').strip()

                    # Upsert Call
                    # First ensure User exists
                    user, _ = User.objects.get_or_create(phone_number=caller_id, defaults={'username': caller_id})

                    call, created = Call.objects.update_or_create(
                        session_id=session_id,
                        defaults={
                            'user': user,
                            'caller_id': caller_id,
                            'wav_filename': file,
                            'txt_filename': txt_filename,
                            'wav_size': wav_size,
                            'txt_size': txt_size,
                            'created_at': created_at,
                            'transfer_reasons': transfer_reasons,
                            'transfer_reason_descriptions': transfer_reason_descriptions,
                        }
                    )
                    
                    if created:
                        count_created += 1
                        self.stdout.write(self.style.SUCCESS(f"Created call {session_id}"))
                    else:
                        count_updated += 1
                        # Update timestamp if needed or just count as updated
                        # self.stdout.write(f"Updated call {session_id}")

        self.stdout.write(self.style.SUCCESS(f"Sync complete. Created: {count_created}, Updated: {count_updated}"))
