from flask import Flask, render_template, request, jsonify
from kubernetes import client, config
from kubernetes.client.exceptions import ApiException

app = Flask(__name__)

# kubeconfig 파일 로드
config.load_kube_config()

# CoreV1 API 인스턴스 생성
v1 = client.CoreV1Api()

# 네임스페이스 설정 (기본값은 현재 네임스페이스)
DEFAULT_NAMESPACE = "k8s-api-junehong"

# 네임스페이스 목록 가져오기
def get_namespaces():
    try:
        namespaces = v1.list_namespace()
        return [ns.metadata.name for ns in namespaces.items]
    except ApiException as e:
        print(f"Failed to get namespaces: {e}")
        return []

# Pod 생성 함수
def create_pod(pod_name, namespace, cpu_request, memory_request, volume_size, gpu_request):
    # 메타데이터 설정
    metadata = client.V1ObjectMeta(name=pod_name)

    # 리소스 요청 설정
    resource_requests = {
        "cpu": cpu_request,
        "memory": memory_request
    }

    # GPU 요청이 있는 경우 리소스 요청에 추가
    if gpu_request and int(gpu_request) > 0:
        resource_requests["nvidia.com/gpu"] = gpu_request

    # 리소스 요청 정의
    resources = client.V1ResourceRequirements(requests=resource_requests)

    # 컨테이너 정의
    container = client.V1Container(
        name="example-container",
        image="nginx:latest",
        ports=[client.V1ContainerPort(container_port=80)],
        resources=resources
    )

    # 볼륨 정의
    volume = client.V1Volume(
        name="example-volume",
        empty_dir=client.V1EmptyDirVolumeSource(size_limit=volume_size)
    )

    # 볼륨 마운트 설정 (mount_path 사용)
    volume_mount = client.V1VolumeMount(
        name="example-volume",
        mount_path="/usr/share/nginx/html"
    )

    # 볼륨 마운트를 컨테이너에 추가
    container.volume_mounts = [volume_mount]

    # Pod 스펙 정의
    spec = client.V1PodSpec(containers=[container], volumes=[volume])
    pod = client.V1Pod(api_version="v1", kind="Pod", metadata=metadata, spec=spec)

    # Pod 생성 요청
    try:
        v1.create_namespaced_pod(namespace=namespace, body=pod)
        return f"Pod '{pod_name}' created successfully in namespace '{namespace}'."
    except ApiException as e:
        return f"Failed to create Pod: {e}"


# 생성된 Pod 목록 조회 함수
def list_pods(namespace):
    try:
        pods = v1.list_namespaced_pod(namespace=namespace)
        pod_list = [{"name": pod.metadata.name, "status": pod.status.phase} for pod in pods.items]
        return pod_list
    except ApiException as e:
        return []

# Pod 삭제 함수
def delete_pod(namespace, pod_name):
    try:
        v1.delete_namespaced_pod(name=pod_name, namespace=namespace)
        return f"Pod '{pod_name}' deleted successfully."
    except ApiException as e:
        return f"Failed to delete Pod: {e}"

# 웹 인터페이스
@app.route("/")
def index():
    namespaces = get_namespaces()
    pods = list_pods(DEFAULT_NAMESPACE)
    return render_template("index.html", namespaces=namespaces, pods=pods)

# Pod 생성 요청 처리
@app.route("/create_pod", methods=["POST"])
def create_pod_route():
    pod_name = request.form.get("pod_name")
    namespace = request.form.get("namespace")
    cpu_request = request.form.get("cpu_request")
    memory_request = request.form.get("memory_request")
    volume_size = request.form.get("volume_size")
    gpu_request = request.form.get("gpu_request")
    message = create_pod(pod_name, namespace, cpu_request, memory_request, volume_size, gpu_request)
    return jsonify({"message": message})

# Pod 삭제 요청 처리
@app.route("/delete_pod/<namespace>/<pod_name>", methods=["POST"])
def delete_pod_route(namespace, pod_name):
    message = delete_pod(namespace, pod_name)
    return jsonify({"message": message})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
