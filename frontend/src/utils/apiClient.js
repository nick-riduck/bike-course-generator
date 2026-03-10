import axios from 'axios';
import { auth } from '../firebase';

// 1. 기본 axios 인스턴스 생성
const apiClient = axios.create({
  baseURL: '/', // 모든 요청은 기본적으로 같은 도메인(또는 프록시)으로 향함
  timeout: 10000, // 10초 타임아웃 강제 설정! (서버가 무응답일 때 무한 로딩 방지)
  headers: {
    'Content-Type': 'application/json',
  },
});

// 2. 요청(Request) 인터셉터: API 요청을 보내기 직전에 가로채서 실행
apiClient.interceptors.request.use(
  async (config) => {
    // 현재 로그인된 유저가 있다면 Firebase 토큰을 가져와 Authorization 헤더에 자동 추가
    const user = auth.currentUser;
    if (user) {
      try {
        const idToken = await user.getIdToken();
        config.headers['Authorization'] = `Bearer ${idToken}`;
      } catch (error) {
        console.error('Failed to get Firebase token:', error);
      }
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// 3. 응답(Response) 인터셉터: 서버 응답을 컴포넌트로 전달하기 전에 가로채서 실행
apiClient.interceptors.response.use(
  (response) => {
    // 2xx 범위에 있는 상태 코드는 이 함수를 트리거합니다.
    return response.data; // axios는 기본적으로 { data, status, headers... } 객체를 반환하므로, 실제 데이터(data)만 뽑아서 리턴
  },
  (error) => {
    // 2xx 외의 범위에 있는 상태 코드는 이 함수를 트리거합니다.
    
    // 에러 종류별 중앙 처리 로직
    if (error.code === 'ECONNABORTED' || error.message.includes('timeout')) {
      console.error('API 타임아웃 발생! 서버 응답이 너무 늦습니다.');
      // 여기서 전역 Toast 메시지를 띄우는 등 추가 처리 가능
    } else if (error.response) {
      // 요청이 전송되었고, 서버가 2xx 외의 상태 코드로 응답한 경우
      console.error(`API 에러 [${error.response.status}]:`, error.response.data);
      if (error.response.status === 401) {
        console.warn('인증 토큰이 만료되었거나 유효하지 않습니다. 로그아웃 처리 등이 필요할 수 있습니다.');
      }
    } else if (error.request) {
      // 요청이 전송되었지만, 응답이 수신되지 않은 경우 (네트워크 단절 등)
      console.error('API 무응답 (네트워크 에러):', error.request);
    } else {
      // 오류를 발생시킨 요청을 설정하는 중에 문제가 발생한 경우
      console.error('API 설정 에러:', error.message);
    }

    return Promise.reject(error);
  }
);

export default apiClient;
