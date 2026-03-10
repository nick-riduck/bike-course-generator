from fastapi import APIRouter, HTTPException, Depends
from firebase_admin import auth
from app.core.database import get_db_conn
from app.core.security import get_current_user
from app.models.auth import LoginRequest

router = APIRouter(prefix="/api/auth", tags=["auth"])

@router.post("/login")
async def login(request: LoginRequest):
    try:
        decoded_token = auth.verify_id_token(request.id_token)
        uid = decoded_token['uid']
        email = decoded_token.get('email')
        name = decoded_token.get('name', 'Anonymous Rider')
        picture = decoded_token.get('picture')

        conn = get_db_conn()
        cur = conn.cursor()

        cur.execute(
            "SELECT user_id FROM auth_mapping_temp WHERE provider = 'FIREBASE' AND provider_uid = %s",
            (uid,)
        )
        row = cur.fetchone()

        if row:
            user_id = row['user_id']
            cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            user = cur.fetchone()
        else:
            cur.execute("SELECT COALESCE(MIN(riduck_id), 0) as min_id FROM users WHERE riduck_id < 0")
            min_id = cur.fetchone()['min_id']
            temp_riduck_id = min_id - 1

            cur.execute(
                """
                INSERT INTO users (riduck_id, username, email, profile_image_url) 
                VALUES (%s, %s, %s, %s) RETURNING *
                """,
                (temp_riduck_id, name, email, picture)
            )
            user = cur.fetchone()
            user_id = user['id']

            cur.execute(
                "INSERT INTO auth_mapping_temp (provider, provider_uid, user_id) VALUES ('FIREBASE', %s, %s)",
                (uid, user_id)
            )
            conn.commit()

        cur.close()
        conn.close()

        return {
            "status": "success",
            "user": {
                "id": user['id'],
                "username": user['username'],
                "email": user['email'],
                "profile_image_url": user['profile_image_url'],
                "onboarding_completed": user.get('onboarding_completed', False)
            }
        }

    except Exception as e:
        print(f"Login Error: {e}")
        raise HTTPException(status_code=401, detail=f"Invalid authentication: {str(e)}")


@router.patch("/users/me/onboarding")
async def complete_onboarding(user_id: int = Depends(get_current_user)):
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE users SET onboarding_completed = TRUE WHERE id = %s RETURNING onboarding_completed",
            (user_id,)
        )
        result = cur.fetchone()
        if not result:
            raise HTTPException(status_code=404, detail="User not found")
        conn.commit()
        return {"status": "success", "onboarding_completed": True}
    finally:
        cur.close()
        conn.close()
