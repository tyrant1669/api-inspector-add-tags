
import re
from typing import Any, Dict, List, Optional, Set, Tuple


def extract_api_urls(api_list: List[Dict[str, Any]]) -> List[str]:
    
    return [api.get("url") for api in api_list if "url" in api]


def extract_json_response(api_list: List[Dict[str, Any]], url: str) -> Optional[Any]:
   
    for api in api_list:
        if api.get("url") == url:
            return api.get("data")
    return None


def find_arrays(data: Any) -> Dict[str, List[str]]:
    
    arrays: Dict[str, List[str]] = {}

    def walk(obj: Any, path: str = ""):
        if isinstance(obj, list):
            if len(obj) > 0 and isinstance(obj[0], dict):
               
                arrays[path] = list(obj[0].keys())
           
            for item in obj:
                walk(item, path)
        elif isinstance(obj, dict):
            for k, v in obj.items():
                new_path = f"{path}.{k}" if path else k
                walk(v, new_path)
        
    walk(data)

    
    clean: Dict[str, List[str]] = {}
    for full_path, keys in arrays.items():
        name = full_path.split(".")[-1] if full_path else "root"
        clean[name] = keys
    return clean


def extract_id_objects(data: Any) -> List[Dict[str, Any]]:
   
    found: Dict[str, Set[str]] = {}

    def scan(obj: Any, path: str = ""):
        if isinstance(obj, dict):
           
            numeric_keys = [k for k in obj.keys() if isinstance(k, str) and re.fullmatch(r"\d+", k)]
            if numeric_keys:
                object_name = path.split(".")[-1] if path else "root"
                object_name = object_name.strip() or "root"
                if object_name not in found:
                    found[object_name] = set()
                for nk in numeric_keys:
                    val = obj.get(nk)
                    if isinstance(val, dict):
                        found[object_name].update(val.keys())
          
            for k, v in obj.items():
                new_path = f"{path}.{k}" if path else k
                scan(v, new_path)
        elif isinstance(obj, list):
            for item in obj:
                scan(item, path)

    scan(data)

    results: List[Dict[str, Any]] = []
    for obj_name, keys_set in found.items():
        results.append({
            "object_name": obj_name,
            "key_id": f"{obj_name}_id",
            "keys_list": sorted(list(keys_set))
        })
    return results

def extract_objects_model3(data):

    results = []
    seen = set()

    def scan(obj, path="root", inside_array=False):

       
        if inside_array:
            return

        if isinstance(obj, dict):

            object_name = path.split(".")[-1]
            keys_list = list(obj.keys())

            signature = (object_name, tuple(keys_list))

            if signature not in seen:
                seen.add(signature)
                results.append({
                    "object_name": object_name,
                    "keys_list": keys_list
                })

           
            for k, v in obj.items():
                new_path = f"{path}.{k}" if path else k
                scan(v, new_path, inside_array=False)

        elif isinstance(obj, list):

           
            for item in obj:
                scan(item, path, inside_array=True)

    scan(data, "root", inside_array=False)
    return results


def find_path_of_key(data: Any, target_key: str) -> Optional[str]:
    
    def scan(obj: Any, path: str = "") -> Optional[str]:
        if isinstance(obj, dict):
            for k, v in obj.items():
                new_path = f"{path}.{k}" if path else k
                if k == target_key and isinstance(v, list):
                    return new_path
                r = scan(v, new_path)
                if r:
                    return r
        elif isinstance(obj, list):
            for item in obj:
                r = scan(item, path)
                if r:
                    return r
        return None

    return scan(data, "")


def find_numeric_object_path(data: Any, object_name: str) -> Optional[str]:
   
    def scan(obj: Any, path: str = "") -> Optional[str]:
        if isinstance(obj, dict):
            
            numeric_keys = [k for k in obj.keys() if isinstance(k, str) and re.fullmatch(r"\d+", k)]
            if numeric_keys:
               
                candidate_name = path.split(".")[-1] if path else ""
                if not object_name or candidate_name == object_name:
                    return path or candidate_name or ""
            for k, v in obj.items():
                new_path = f"{path}.{k}" if path else k
                r = scan(v, new_path)
                if r:
                    return r
        elif isinstance(obj, list):
            for item in obj:
                r = scan(item, path)
                if r:
                    return r
        return None

    return scan(data, "")


def get_by_dotpath(data: Any, dotpath: str) -> Any:
   
    if not dotpath:
        return data
    parts = dotpath.split(".")
    cur = data
    for p in parts:
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return None
    return cur


def build_columns_for_object(obj: Dict[str, Any], prefix: str = "") -> List[Dict[str, str]]:
   
    cols: List[Dict[str, str]] = []

    def add(local: Any, cur_prefix: str):
        if not isinstance(local, dict):
            return
        for k, v in local.items():
            new_prefix = f"{cur_prefix}/{k}" if cur_prefix else k
            
            if isinstance(v, list):
                if len(v) > 0 and isinstance(v[0], dict):
                    add(v[0], new_prefix)
                
                continue
            if isinstance(v, dict):
                add(v, new_prefix)
                continue
         
            cols.append({
                "path": f"./{new_prefix}",
                "dataType": "string",
                "columnName": k
            })

    add(obj, prefix)
    return cols
