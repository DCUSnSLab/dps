from flask import Flask, render_template, request, jsonify
from kubernetes import client, config
from kubernetes.client.exceptions import ApiException
import threading
import time

app = Flask(__name__)

# kubeconfig 파일 로드
config.load_kube_config()

# V1 API 인스턴스 생성
v1 = client.CoreV1Api()

# 현재 네임스페이스 가져오기
current_namespace = "k8s-api-junehong"

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
    metadata = client.V1ObjectMeta(name=pod_name, labels={"app": "example"})
    resources = client.V1ResourceRequirements(
        requests={
            "cpu": cpu_request,
            "memory": memory_request
        },
        limits={
            "nvidia.com/gpu": gpu_request
        }
    )

    container = client.V1Container(
        name="example-container",
        image="nginx:latest",
        ports=[client.V1ContainerPort(container_port=80)],
        resources=resources
    )

    volume = client.V1Volume(
        name="example-volume",
        empty_dir=client.V1EmptyDirVolumeSource(size_limit=volume_size)
    )

    volume_mount = client.V1VolumeMount(
        name="example-volume",
        mount_path="/usr/share/nginx/html"
    )

    container.volume_mounts = [volume_mount]
    spec = client.V1PodSpec(containers=[container], volumes=[volume])
    pod = client.V1Pod(api_version="v1", kind="Pod", metadata=metadata, spec=spec)

    try:
        v1.create_namespaced_pod(namespace=namespace, body=pod)
        return f"Pod '{pod_name}' created successfully in namespace '{namespace}'."
    except ApiException as e:
        return f"Failed to create Pod: {e}"

# Pod 목록 조회 함수
def list_pods(namespace):
    try:
        pods = v1.list_namespaced_pod(namespace=namespace)
        pod_list = [{"name": pod.metadata.name, "status": pod.status.phase} for pod in pods.items]
        return pod_list
    except ApiException as e:
        return []

# Pod 삭제 함수
def delete_pod(pod_name, namespace):
    try:
        v1.delete_namespaced_pod(name=pod_name, namespace=namespace)
        return f"Pod '{pod_name}' deleted successfully."
    except ApiException as e:
        return f"Failed to delete Pod: {e}"

# GPU 정보 조회 함수
def get_gpu_info():
    # GPU 정보 조회 로직 추가 필요 (NVML 라이브러리 사용 가능)
    return []

# 웹 인터페이스
@app.route("/")
def index():
    namespaces = get_namespaces()
    pods = list_pods(current_namespace)
    gpu_info = get_gpu_info()
    return render_template("index.html", namespaces=namespaces, pods=pods, gpu_info=gpu_info)

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
    message = delete_pod(pod_name, namespace)
    return jsonify({"message": message})

# Pod 목록 실시간 갱신
@app.route("/list_pods/<namespace>")
def list_pods_route(namespace):
    pods = list_pods(namespace)
    return jsonify(pods)

# 실시간 업데이트 스레드
def update_pod_status():
    while True:
        time.sleep(10)
        list_pods(current_namespace)

if __name__ == "__main__":
    threading.Thread(target=update_pod_status).start()
    app.run(host="0.0.0.0", port=5000)
