import os
import json
from flask import Flask, render_template, request, jsonify
from kubernetes import client, config
from kubernetes.client.exceptions import ApiException


class KubernetesManager:
    def __init__(self):
        # kubeconfig 파일 로드
        config.load_kube_config()
        self.v1 = client.CoreV1Api()

    def get_namespaces(self):
        try:
            namespaces = self.v1.list_namespace()
            return [ns.metadata.name for ns in namespaces.items]
        except ApiException as e:
            print(f"Failed to get namespaces: {e}")
            return []

    def get_image_list(self):
        try:
            with open("docker_images.json", "r") as file:
                image_data = json.load(file)
            return image_data
        except Exception as e:
            print(f"Failed to load image list: {e}")
            return {}

    def convert_memory_to_mib(self, memory_str):
        if memory_str.endswith("Gi"):
            return int(float(memory_str.replace("Gi", "")) * 1024)
        elif memory_str.endswith("Mi"):
            return int(memory_str.replace("Mi", ""))
        elif memory_str.endswith("Ki"):
            return int(float(memory_str.replace("Ki", "")) / 1024)
        elif memory_str.isdigit():
            return int(memory_str)
        return 0

    def list_pods(self, namespace):
        try:
            pods = self.v1.list_namespaced_pod(namespace=namespace)
            pod_list = []
            for pod in pods.items:
                cpu_requests = 0
                cpu_limits = 0
                memory_requests = 0
                memory_limits = 0
                gpu_requests = 0

                for container in pod.spec.containers:
                    resources = container.resources
                    requests = resources.requests or {}
                    limits = resources.limits or {}

                    cpu_requests += float(requests.get("cpu", "0").replace("m", "")) / 1000
                    cpu_limits += float(limits.get("cpu", "0").replace("m", "")) / 1000
                    memory_requests += self.convert_memory_to_mib(requests.get("memory", "0"))
                    memory_limits += self.convert_memory_to_mib(limits.get("memory", "0"))
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

    def get_available_gpus(self):
        try:
            nodes = self.v1.list_node()
            available_gpus = []
            for node in nodes.items:
                gpu_capacity = node.status.capacity.get("nvidia.com/gpu", "0")
                gpu_allocatable = node.status.allocatable.get("nvidia.com/gpu", "0")
                if int(gpu_capacity) > 0:
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

    def create_pod(self, pod_name, namespace, image, cpu_request, memory_request, volume_size, use_gpu):
        pod_name = pod_name.replace("_", "-")
        metadata = client.V1ObjectMeta(name=pod_name)

        resource_requests = {"cpu": cpu_request, "memory": memory_request}
        resource_limits = {"cpu": cpu_request, "memory": memory_request}
        if use_gpu:
            resource_requests["nvidia.com/gpu"] = "1"
            resource_limits["nvidia.com/gpu"] = "1"

        resources = client.V1ResourceRequirements(requests=resource_requests, limits=resource_limits)
        container = client.V1Container(
            name=pod_name, image=image, ports=[client.V1ContainerPort(container_port=80)], resources=resources,
            command=["/bin/bash", "-c", "while true; do sleep 30; done"]
        )
        spec = client.V1PodSpec(containers=[container])
        pod = client.V1Pod(api_version="v1", kind="Pod", metadata=metadata, spec=spec)

        try:
            self.v1.create_namespaced_pod(namespace=namespace, body=pod)
            return f"Pod '{pod_name}' created successfully in namespace '{namespace}'."
        except ApiException as e:
            return f"Failed to create Pod: {e}"

    def delete_pod(self, namespace, pod_name):
        try:
            self.v1.delete_namespaced_pod(name=pod_name, namespace=namespace)
            return f"Pod '{pod_name}' deleted successfully."
        except ApiException as e:
            return f"Failed to delete Pod: {e}"


class FlaskApp:
    def __init__(self):
        self.app = Flask(__name__)
        self.k8s_manager = KubernetesManager()
        self.setup_routes()

    def setup_routes(self):
        @self.app.route("/")
        def index():
            namespaces = self.k8s_manager.get_namespaces()
            gpus = self.k8s_manager.get_available_gpus()
            return render_template("index.html", namespaces=namespaces, gpus=gpus)

        @self.app.route("/list_pods/<namespace>")
        def list_pods_route(namespace):
            pods = self.k8s_manager.list_pods(namespace)
            return jsonify(pods)

        @self.app.route("/get_images")
        def get_images():
            images = self.k8s_manager.get_image_list()
            return jsonify(images)

        @self.app.route("/delete_pod/<namespace>/<pod_name>", methods=["POST"])
        def delete_pod_route(namespace, pod_name):
            message = self.k8s_manager.delete_pod(namespace, pod_name)
            return jsonify({"message": message})

        @self.app.route("/create_pod", methods=["POST"])
        def create_pod_route():
            data = request.form
            message = self.k8s_manager.create_pod(
                data.get("pod_name"), data.get("namespace"), data.get("image"),
                data.get("cpu_request"), data.get("memory_request"),
                data.get("volume_size"), data.get("use_gpu") == "on"
            )
            return jsonify({"message": message})

    def run(self):
        self.app.run(host="0.0.0.0", port=5000)


if __name__ == "__main__":
    FlaskApp().run()
