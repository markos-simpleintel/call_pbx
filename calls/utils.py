import os
import datetime
from django.utils.timezone import make_aware
from django.conf import settings
from calls.models import Call, User

def process_call_file(wav_path, stdout=None, style=None):
    """
    Process a single call file and create/update the Call record.
    Returns True if successful, False otherwise.
    """
    try:
        # Path structure: .../caller_id/filename.wav
        dir_path = os.path.dirname(wav_path)
        caller_id = os.path.basename(dir_path)
        filename = os.path.basename(wav_path)

        # Extract Session ID
        # format: {caller_id}_{session_id}_full.wav
        base_name = filename.replace('_full.wav', '')
        
        parts = base_name.split('_')
        session_id = parts[1] if len(parts) >= 2 else base_name

        # Check if User exists
        user = User.objects.filter(phone_number=caller_id).first()
        if not user:
            if stdout:
                stdout.write(style.WARNING(f"File from {caller_id}: User not registered. Saving as unassociated."))

        relative_path = os.path.join(caller_id, filename)

        # Normal _full.wav processing
        txt_filename = filename.replace('_full.wav', '_full.txt')
        txt_path = os.path.join(dir_path, txt_filename)

        # Check for conversation file in sibling directory: ../{caller_session}/full_conversation.wav
        sounds_root = os.path.abspath(os.path.join(dir_path, '../../')) 
        conversation_dir = os.path.join(sounds_root, base_name) # base_name is {caller_id}_{session_id}
        conversation_file_path = os.path.join(conversation_dir, 'full_conversation.wav')
        
        full_conv_relative = None
        if os.path.exists(conversation_file_path):
            full_conv_relative = os.path.join('..', base_name, 'full_conversation.wav')
            if stdout:
                stdout.write(f"Found conversation file at {full_conv_relative}")

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
                if stdout:
                    stdout.write(style.ERROR(f"Error reading txt file: {e}"))

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
        # Only update full_conversation_filename if we found it
        if full_conv_relative:
            defaults['full_conversation_filename'] = full_conv_relative

        Call.objects.update_or_create(
            session_id=session_id,
            defaults=defaults
        )
        if stdout:
             stdout.write(style.SUCCESS(f"Processed match call {session_id}"))
        return True

    except Exception as e:
        if stdout:
            stdout.write(style.ERROR(f"Error processing file {wav_path}: {e}"))
        return False

def scan_user_folder(phone_number):
    """
    Scans the specific folder for a user and imports all calls.
    Used when a new user registers.
    """
    recordings_root = getattr(settings, 'RECORDINGS_ROOT', '/usr/local/share/asterisk/sounds/call_sessions')
    user_dir = os.path.join(recordings_root, phone_number)
    
    if os.path.exists(user_dir):
        # We don't have access to stdout/style here easily, so we skip logging or use standard logging
        # For now we just process silently or print to console (which goes to docker logs)
        print(f"Scanning folder for new user: {phone_number}")
        for root, dirs, files in os.walk(user_dir):
            for file in files:
                if file.endswith('_full.wav'):
                    process_call_file(os.path.join(root, file))
