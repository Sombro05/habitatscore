import os
from supabase import create_client

def get_client():
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_KEY", "")
    if not url or not key:
        return None
    return create_client(url, key)

def track(type, source=None, ville=None, type_bien=None,
          score=None, filtre_val=None, session_id=None, user_agent=None):
    try:
        client = get_client()
        if not client:
            return
        client.table("events").insert({
            "type":       type,
            "source":     source,
            "ville":      ville,
            "type_bien":  type_bien,
            "score":      score,
            "filtre_val": filtre_val,
            "session_id": session_id,
            "user_agent": user_agent,
        }).execute()
    except Exception:
        pass  # Ne jamais bloquer l'app si le tracking échoue

def feedback(note, commentaire=None, email=None, source=None, session_id=None):
    try:
        client = get_client()
        if not client:
            return
        client.table("feedbacks").insert({
            "note":        note,
            "commentaire": commentaire,
            "email":       email,
            "source":      source,
            "session_id":  session_id,
        }).execute()
    except Exception:
        pass