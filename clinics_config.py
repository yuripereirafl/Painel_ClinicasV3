import os
import json

# Lista oficial das Clínicas e seus endpoints na VPN
DEFAULT_CLINIC_NODES = [
    {
        "id": 1,
        "name": "Dr. Flores 47",
        "ip": "192.168.18.40:5000",
        "url": "http://192.168.18.40:5000",
        "clinic_id": 2,
        "is_local": False
    },
    {
        "id": 2,
        "name": "Canoas",
        "ip": "192.168.6.75:5000",
        "url": "http://192.168.6.75:5000",
        "clinic_id": 3,
        "is_local": False
    },
    {
        "id": 3,
        "name": "Cachoeirinha",
        "ip": "192.168.7.75:5000",
        "url": "http://192.168.7.75:5000",
        "clinic_id": 3,
        "is_local": False
    },
    {
        "id": 4,
        "name": "Azenha",
        "ip": "192.168.12.75:5000",
        "url": "http://192.168.12.75:5000",
        "clinic_id": 3,
        "is_local": False
    },
    {
        "id": 5,
        "name": "Alvorada",
        "ip": "192.168.8.70:5000",
        "url": "http://192.168.8.70:5000",
        "clinic_id": 3,
        "is_local": False
    },
    {
        "id": 6,
        "name": "Gravataí",
        "ip": "192.168.14.75:5000",
        "url": "http://192.168.14.75:5000",
        "clinic_id": 1,
        "is_local": False
    },
    {
        "id": 7,
        "name": "Assis Odonto",
        "ip": "192.168.11.75:5000",
        "url": "http://192.168.11.75:5000",
        "clinic_id": 3,
        "is_local": False
    },
    {
        "id": 8,
        "name": "Assis Brasil 3277",
        "ip": "192.168.5.56:5000",
        "url": "http://192.168.5.56:5000",
        "clinic_id": 3,
        "is_local": False
    }
]

def get_clinic_nodes():
    """Retorna a lista de nós/clínicas. Pode ser customizado via variável de ambiente CLINIC_NODES (JSON)."""
    nodes_env = os.getenv('CLINIC_NODES')
    if nodes_env:
        try:
            return json.loads(nodes_env)
        except Exception as e:
            print(f"Erro ao parsear CLINIC_NODES do ambiente: {e}")
    return DEFAULT_CLINIC_NODES
