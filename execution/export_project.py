#!/usr/bin/env python3
"""
Utility script to list all Firestore projects and export a complete, consolidated
project production table JSON. Useful for downloading user data and recovering lost tables.
"""

import os
import sys
import json
from datetime import datetime

# Add the current directory to sys.path so we can import firestore_helpers
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import firebase_admin
from firebase_admin import credentials, firestore
import firestore_helpers as fh

# Initialize Firebase using the standard service account
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
SERVICE_ACCOUNT_PATH = os.path.join(PROJECT_DIR, "firebase-service-account.json")

if not os.path.exists(SERVICE_ACCOUNT_PATH):
    print(f"Error: Firebase service account JSON not found at: {SERVICE_ACCOUNT_PATH}", file=sys.stderr)
    sys.exit(1)

if not firebase_admin._apps:
    try:
        cred = credentials.Certificate(SERVICE_ACCOUNT_PATH)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        print(f"Error initializing Firebase Admin SDK: {e}", file=sys.stderr)
        sys.exit(1)

db = firestore.client()

def serialize_datetime(obj):
    """Serialize datetime objects to ISO format."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, 'isoformat'):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")

def list_all_projects():
    """Scan all users and list their projects."""
    print("Scanning Firestore database for users and projects...\n")
    users = db.collection('users').stream()
    
    projects_list = []
    
    for user_doc in users:
        uid = user_doc.id
        # Let's see if this user has any projects
        projects = db.collection('users').document(uid).collection('projects').stream()
        for proj_doc in projects:
            pid = proj_doc.id
            pdata = proj_doc.to_dict() or {}
            title = pdata.get('title', 'Untitled Project')
            
            # Count shots and visuals
            try:
                shot_count = fh.shots_count(uid, pid)
            except Exception:
                shot_count = 0
                
            try:
                visual_count = len(fh.read_visuals(uid, pid))
            except Exception:
                visual_count = 0
                
            last_updated = pdata.get('last_updated_at') or pdata.get('created_at') or "N/A"
            if hasattr(last_updated, 'isoformat'):
                last_updated = last_updated.isoformat()
                
            projects_list.append({
                'uid': uid,
                'pid': pid,
                'title': title,
                'shots': shot_count,
                'visuals': visual_count,
                'last_updated': last_updated
            })
            
    if not projects_list:
        print("No users or projects found in Firestore.")
        return
        
    # Print a beautiful table of projects
    print(f"{'INDEX':<6} | {'USER ID (uid)':<32} | {'PROJECT ID (pid)':<32} | {'PROJECT TITLE':<30} | {'SHOTS':<6} | {'VISUALS':<8} | {'LAST UPDATED':<20}")
    print("-" * 150)
    for idx, p in enumerate(projects_list):
        title_truncated = p['title'][:28] + ".." if len(p['title']) > 28 else p['title']
        print(f"{idx:<6} | {p['uid']:<32} | {p['pid']:<32} | {title_truncated:<30} | {p['shots']:<6} | {p['visuals']:<8} | {p['last_updated'][:20]}")
    
    print("\nTo export a project to JSON, run:")
    print(f"  python3 execution/export_project.py <uid> <pid>")

def export_project(uid, pid):
    """Retrieve full project details and export them to a consolidated JSON file."""
    print(f"Fetching project '{pid}' for user '{uid}' from Firestore...")
    
    # 1. Fetch main project document
    doc_ref = db.collection('users').document(uid).collection('projects').document(pid)
    doc = doc_ref.get()
    if not doc.exists:
        print(f"Error: Project '{pid}' for user '{uid}' not found.", file=sys.stderr)
        sys.exit(1)
        
    project_data = doc.to_dict()
    project_data['id'] = doc.id
    
    # 2. Lazy migration just in case
    try:
        migrated = fh.migrate_project(uid, pid, project_data)
        if migrated:
            print("Notice: Auto-migrated legacy embedded project data to subcollections.")
            project_data.pop('production_data', None)
            project_data.pop('visuals_scenes', None)
    except Exception as mig_err:
        print(f"Warning during migration check: {mig_err}", file=sys.stderr)
        
    # 3. Read shots
    print("Reading shots subcollection...")
    shots = fh.read_shots(uid, pid)
    if shots:
        project_data['production_data'] = {
            'production_table': {
                'shots': shots,
                'total_shots': len(shots)
            }
        }
        print(f"Loaded {len(shots)} shots.")
    else:
        print("No shots found.")
        
    # 4. Read visuals
    print("Reading visuals subcollection...")
    visuals = fh.read_visuals(uid, pid)
    if visuals:
        project_data['visuals_scenes'] = visuals
        print(f"Loaded {len(visuals)} visuals.")
    else:
        print("No visuals found.")
        
    # 5. Read checkpoints
    print("Reading pipeline checkpoints...")
    project_data['pipeline_state'] = fh.read_checkpoints(uid, pid)
    
    # Convert timestamps
    for key in ('created_at', 'last_updated_at', 'migrated_at'):
        if key in project_data and hasattr(project_data[key], 'isoformat'):
            project_data[key] = project_data[key].isoformat()
            
    # Prepare export paths
    project_title = project_data.get('title', 'exported_project').replace('/', '_').replace(' ', '_')
    timestamp = int(datetime.now().timestamp())
    filename = f"production_table_{project_title}_{timestamp}.json"
    
    tmp_dir = os.path.join(PROJECT_DIR, ".tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    export_path = os.path.join(tmp_dir, filename)
    
    # Save the consolidated JSON
    with open(export_path, 'w', encoding='utf-8') as f:
        json.dump(project_data, f, default=serialize_datetime, indent=2)
        
    print(f"\nSUCCESS! Consistently stitched and exported project JSON.")
    print(f"Project Title: {project_data.get('title')}")
    print(f"Exported File: {export_path}")
    print(f"\nYou can now open or download this JSON file directly.")
    return export_path

if __name__ == '__main__':
    if len(sys.argv) == 1:
        list_all_projects()
    elif len(sys.argv) == 3:
        export_project(sys.argv[1], sys.argv[2])
    else:
        print("Usage:")
        print("  List projects:   python3 execution/export_project.py")
        print("  Export project:  python3 execution/export_project.py <uid> <pid>")
        sys.exit(1)
