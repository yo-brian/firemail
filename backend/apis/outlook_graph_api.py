import msal
import json
from flask import Blueprint, request, jsonify
from backend.db.models import Email, db
import threading
import time

outlook_graph_api = Blueprint('outlook_graph_api', __name__)

# IMPORTANT: Replace with your Azure AD application's details
# You can get these from the Azure portal
CLIENT_ID = "23e659ad-e020-4a5e-b0a1-f2fe15ee535c" 
AUTHORITY = "https://login.microsoftonline.com/common"

# This will store the device flow and the result of the authentication
# For a production app, you might want to use a database or a more persistent cache
flow_cache = {}

@outlook_graph_api.route('/initiate', methods=['POST'])
def initiate_device_flow():
    """Initiates the device flow for Microsoft Graph authentication."""
    try:
        app = msal.PublicClientApplication(CLIENT_ID, authority=AUTHORITY)
        flow = app.initiate_device_flow(scopes=["https://graph.microsoft.com/Mail.Read", "offline_access"])

        if "user_code" not in flow:
            return jsonify({'success': False, 'message': 'Failed to initiate device flow.'}), 500

        # Store the flow for polling
        device_code = flow['device_code']
        flow_cache[device_code] = {'flow': flow, 'result': None}

        return jsonify({
            'success': True,
            'user_code': flow['user_code'],
            'verification_uri': flow['verification_uri'],
            'expires_in': flow['expires_in'],
            'interval': flow['interval'],
            'device_code': device_code  # Sending device_code to frontend to poll
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

def _acquire_token_silently(device_code):
    """Helper function to run in a background thread to acquire the token."""
    if device_code not in flow_cache:
        return

    flow_info = flow_cache[device_code]
    app = msal.PublicClientApplication(CLIENT_ID, authority=AUTHORITY)
    
    # Poll for the token
    result = app.acquire_token_by_device_flow(flow_info['flow'])
    
    if "access_token" in result:
        # Authentication successful
        # We can now get user information and save the account
        
        # Here you would typically use the access token to get the user's email
        # For example, by calling the /me endpoint of Microsoft Graph
        import requests
        headers = {'Authorization': 'Bearer ' + result['access_token']}
        graph_response = requests.get('https://graph.microsoft.com/v1.0/me', headers=headers)
        
        if graph_response.status_code == 200:
            user_data = graph_response.json()
            username = user_data.get('userPrincipalName') # Or 'mail'

            if username:
                # Check if email already exists
                existing = Email.query.filter_by(username=username).first()
                if not existing:
                    # Save the new email account
                    new_email = Email(
                        username=username,
                        password=json.dumps(result), # Store the whole token result (including refresh token)
                        type='graph',
                        status='active'
                    )
                    db.session.add(new_email)
                    db.session.commit()
                    flow_info['result'] = {'success': True, 'username': username}
                else:
                    flow_info['result'] = {'success': False, 'message': 'Email already exists.'}
            else:
                flow_info['result'] = {'success': False, 'message': 'Could not retrieve user email from Graph.'}
        else:
            flow_info['result'] = {'success': False, 'message': 'Failed to get user info from Graph.'}
    else:
        flow_info['result'] = result # Could be an error


@outlook_graph_api.route('/check/<device_code>', methods=['GET'])
def check_device_flow(device_code):
    """Checks the status of the device flow authentication."""
    if device_code not in flow_cache:
        return jsonify({'status': 'expired', 'message': 'Device code has expired or is invalid.'}), 404

    # Check if the polling thread is already running
    if 'thread' not in flow_cache[device_code]:
         # Start a background thread to poll for the token
        thread = threading.Thread(target=_acquire_token_silently, args=(device_code,))
        thread.daemon = True
        thread.start()
        flow_cache[device_code]['thread'] = thread
        return jsonify({'status': 'pending', 'message': 'Authentication is pending. Please continue on the verification URI.'})

    result = flow_cache[device_code].get('result')

    if result:
        # Polling is finished
        del flow_cache[device_code] # Clean up
        if result.get('success'):
            return jsonify({'status': 'completed', 'username': result['username']})
        else:
            return jsonify({'status': 'failed', 'message': result.get('error_description', 'Authentication failed.')})
    else:
        return jsonify({'status': 'pending', 'message': 'Authentication is pending. Please continue on the verification URI.'})
