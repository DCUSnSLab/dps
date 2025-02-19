import os
import json
from flask import Flask, render_template, request, jsonify
from kubernetes import client, config
from kubernetes.client.exceptions import ApiException

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)

# kubeconfig 파일 로드
config.load_kube_config()

v1 = client.CoreV1Api()

# 네임스페이스 목록 조회
def get_namespaces():
    try:
        namespaces = v1.list_namespace()
        return [ns.metadata.name for ns in namespaces.items]
    except ApiException as e:
        print(f"Failed to get namespaces: {e}")
        return []

def get_image_list():
    try:
        with open("docker_images.json", "r") as file:
            image_data = json.load(file)
            print(image_data)
        return image_data
    except Exception as e:
        print(f"Failed to load image list: {e}")
        return {}

def convert_memory_to_mib(memory_str):
    if memory_str.endswith("Gi"):  # 기가바이트 → 메가바이트 변환
        return int(float(memory_str.replace("Gi", "")) * 1024)
    elif memory_str.endswith("Mi"):  # 그대로 메가바이트
        return int(memory_str.replace("Mi", ""))
    elif memory_str.endswith("Ki"):  # 킬로바이트 → 메가바이트 변환
        return int(float(memory_str.replace("Ki", "")) / 1024)
    elif memory_str.isdigit():  # 숫자만 있으면 그대로 반환
        return int(memory_str)
    else:
        return 0  # 알 수 없는 형식이면 0으로 처리

def list_pods(namespace):
    try:
        pods = v1.list_namespaced_pod(namespace=namespace)
        pod_list = []
        for pod in pods.items:
            cpu_requests = 0
            cpu_limits = 0
            memory_requests = 0
            memory_limits = 0
            gpu_requests = 0

            # 각 컨테이너의 자원 요청 및 제한 정보 조회
            for container in pod.spec.containers:
                resources = container.resources
                requests = resources.requests or {}
                limits = resources.limits or {}

                # CPU, 메모리, GPU 정보 추출
                cpu_requests += float(requests.get("cpu", "0").replace("m", "")) / 1000
                cpu_limits += float(limits.get("cpu", "0").replace("m", "")) / 1000

                memory_requests += convert_memory_to_mib(requests.get("memory", "0"))
                memory_limits += convert_memory_to_mib(limits.get("memory", "0"))

                gpu_requests += int(requests.get("nvidia.com/gpu", "0"))

            pod_list.append({
                "name": pod.metadata.name,
                "status": pod.status.phase,
                "cpu_requests": f"{cpu_requests:.2f} cores",
                "cpu_limits": f"{cpu_limits:.2f} cores",
                "memory_requests": f"{memory_requests:.2f} Mi",
                "memory_limits": f"{memory_limits:.2f} Mi",
                "gpu_requests": gpu_requests
            })
        return pod_list
    except ApiException as e:
        print(f"Failed to list pods in namespace '{namespace}': {e}")
        return []

# 사용 가능한 GPU 목록 조회 (Kubernetes API 사용)
def get_available_gpus():
    try:
        nodes = v1.list_node()
        available_gpus = []

        for node in nodes.items:
            # GPU가 있는 노드인지 확인
            gpu_capacity = node.status.capacity.get("nvidia.com/gpu", "0")
            gpu_allocatable = node.status.allocatable.get("nvidia.com/gpu", "0")

            if int(gpu_capacity) > 0:
                # 사용 가능한 GPU 수량 계산
                used_gpus = int(gpu_capacity) - int(gpu_allocatable)
                total_gpus = int(gpu_capacity)
                available_gpus.append({
                    "node": node.metadata.name,
                    "total_gpus": total_gpus,
                    "used_gpus": used_gpus,
                    "available_gpus": total_gpus - used_gpus
                })

        return available_gpus
    except ApiException as e:
        print(f"Failed to retrieve GPU information: {e}")
        return []

# Pod 생성 함수
def create_pod(pod_name, namespace, image, cpu_request, memory_request, volume_size, use_gpu):
    pod_name = pod_name.replace("_", "-")
    metadata = client.V1ObjectMeta(name=pod_name)

    resource_requests = {
        "cpu": cpu_request,
        "memory": memory_request
    }
    resource_limits = {
        "cpu": cpu_request,
        "memory": memory_request
    }

    if use_gpu:
        resource_requests["nvidia.com/gpu"] = "1"
        resource_limits["nvidia.com/gpu"] = "1"

    resources = client.V1ResourceRequirements(
        requests=resource_requests,
        limits=resource_limits
    )

    container = client.V1Container(
        name="example-container",
        image=image,
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

def delete_pod(namespace, pod_name):
    try:
        v1.delete_namespaced_pod(name=pod_name, namespace=namespace)
        return f"Pod '{pod_name}' deleted successfully."
    except ApiException as e:
        return f"Failed to delete Pod: {e}"

@app.route("/")
def index():
    namespaces = get_namespaces()
    gpus = get_available_gpus()
    return render_template("index.html", namespaces=namespaces, gpus=gpus)

@app.route("/list_pods/<namespace>")
def list_pods_route(namespace):
    pods = list_pods(namespace)
    return jsonify(pods)

# 이미지 목록 조회 엔드포인트
@app.route("/get_images")
def get_images():
    images = get_image_list()
    return jsonify(images)

# Pod 삭제 엔드포인트
@app.route("/delete_pod/<namespace>/<pod_name>", methods=["POST"])
def delete_pod_route(namespace, pod_name):
    message = delete_pod(namespace, pod_name)
    return jsonify({"message": message})

@app.route("/create_pod", methods=["POST"])
def create_pod_route():
    pod_name = request.form.get("pod_name")
    namespace = request.form.get("namespace")
    image = request.form.get("image")
    cpu_request = request.form.get("cpu_request")
    memory_request = request.form.get("memory_request")
    volume_size = request.form.get("volume_size")
    use_gpu = request.form.get("use_gpu") == "on"

    message = create_pod(pod_name, namespace, image, cpu_request, memory_request, volume_size, use_gpu)
    return jsonify({"message": message})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

