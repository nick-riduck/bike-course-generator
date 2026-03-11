import firebase_admin
from firebase_admin import auth
from fastapi import HTTPException, Header, Depends
from app.core.database import get_db_conn

# Initialize Firebase
try:
    if not firebase_admin._apps:
        firebase_admin.initialize_app()
        print("Firebase Admin Initialized")
except Exception as e:
    print(f"Firebase Init Warning: {e}")

async def get_current_user(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    token = authorization.split(" ")[1]
    try:
        decoded_token = auth.verify_id_token(token)
        uid = decoded_token['uid']

        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT user_id FROM auth_mapping_temp WHERE provider = 'FIREBASE' AND provider_uid = %s",
            (uid,)
        )
        row = cur.fetchone()
        cur.close()
        conn.close()

        if not row:
            raise HTTPException(status_code=401, detail="User not found")

        return row['user_id']
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))


async def get_admin_user(user_id: int = Depends(get_current_user)):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("SELECT is_admin FROM users WHERE id = %s", (user_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row or not row['is_admin']:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user_id
