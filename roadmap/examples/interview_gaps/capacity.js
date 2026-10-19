import http from 'k6/http';
import { check } from 'k6';

const target = __ENV.TARGET || 'http://127.0.0.1:8080/tasks?limit=20';
if (!/^http:\/\/127\.0\.0\.1:8080\//.test(target)) {
  throw new Error('Учебный сценарий разрешает только 127.0.0.1:8080');
}
const rate = Number(__ENV.RATE || 5);
if (!Number.isInteger(rate) || rate < 1 || rate > 50) {
  throw new Error('RATE должен быть целым числом от 1 до 50');
}
http.setResponseCallback(http.expectedStatuses(200));
export const options = {
  scenarios: {
    reads: {
      executor: 'constant-arrival-rate',
      rate, timeUnit: '1s', duration: '30s',
      preAllocatedVUs: 4, maxVUs: 20,
      gracefulStop: '3s'
    }
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<200'],
    checks: ['rate==1'],
    dropped_iterations: ['count==0']
  }
};
export default function () {
  const response = http.get(target, {
    timeout: '2s', redirects: 0,
    tags: { name: 'GET task-list' }
  });
  check(response, { 'HTTP 200': r => r.status === 200 });
}
