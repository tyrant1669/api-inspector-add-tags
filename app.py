
import os
import re
import json
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from flask_wtf.csrf import CSRFProtect


from scraper import fetch_webpage
from parser import (
    extract_json_response,
    find_arrays,
    extract_id_objects,
    extract_objects_model3,
    find_numeric_object_path,
    get_by_dotpath
)

from database import Base, engine, SessionLocal, API, Data, Mapper, Tag, api_tags, db_session
from sqlalchemy import create_engine, Column, Integer, Text, String, ForeignKey, Table, func
from tags import add_tags_to_api, remove_tag_from_api, get_apis_by_tag, get_all_tags
#from flask_wtf.csrf import CSRFProtect

Base.metadata.create_all(bind=engine)

app = Flask(__name__)
app.secret_key = "secret"
app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024
app.config['WTF_CSRF_ENABLED'] = True
app.config['WTF_CSRF_SECRET_KEY'] = 'a-secure-secret-key'  # Change this to a secure secret key

# Initialize CSRF protection
csrf = CSRFProtect(app)
_cached_apis = []


@app.template_test('in')
def is_in(collection, value):
    return value in collection

def get_or_create_api(api_url_str, response_obj):
    
    with db_session() as session:
        existing = session.query(API).filter(API.api == api_url_str).first()
        if existing:
            return existing.id 

       
        api = API(api=api_url_str, response=json.dumps(response_obj))
        session.add(api)
        session.commit()
        session.refresh(api)
        return api.id


def save_data_and_get_id(mode, keys_list, mapping_json):
    with db_session() as session:
        data = Data(
            mode=str(mode),
            keys=json.dumps(keys_list),
            mapping=json.dumps(mapping_json)
        )
        session.add(data)
        session.commit()
        session.refresh(data)
        return data.id


def create_mapper(api_id, data_id):
    with db_session() as session:
        m = Mapper(api_id=api_id, data_id=data_id)
        session.add(m)
        session.commit()

@app.route("/")
def home():
    return render_template("home.html")


@app.route("/url-mode")
def url_mode():
    return render_template("index.html")


@app.route("/header-mode")
def header_mode():
    return render_template("header_input.html")


@app.route("/submit-header", methods=["POST"])
def submit_header():
    global _cached_apis

    headers = request.form.get("headers", "").strip()
    response_text = request.form.get("response", "")

    if response_text and len(response_text.encode("utf-8")) > 1 * 1024 * 1024:
        return "❌ Error: Response too large."

    try:
        json_data = json.loads(response_text)
    except:
        return "Invalid JSON"

    api_label = headers if headers else "pasted-input"

    _cached_apis = [{
        "url": api_label,
        "status": 200,
        "method": "PASTE",
        "data": json_data
    }]

    return render_template("choose_mode.html", api_url=api_label)


@app.route("/fetch", methods=["POST"])
def fetch():
    global _cached_apis

    url = request.form.get("url", "").strip()
    if not url:
        return redirect(url_for("url_mode"))

    if not url.startswith("http"):
        url = "https://" + url

    _cached_apis = fetch_webpage(url)
    apis = [a for a in _cached_apis if a.get("data")]

    return render_template("results.html", apis=apis, site=url)


@app.route("/response", methods=["POST"])
def response():
    url = request.form.get("api_url")
    data = extract_json_response(_cached_apis, url)
    pretty = json.dumps(data, indent=2)
    return render_template("response.html", api_url=url, data=pretty)


@app.route("/choose-extract-mode", methods=["POST"])
def choose_extract_mode():
    api_url = request.form.get("api_url")
    return render_template("choose_mode.html", api_url=api_url)


@app.route("/extract", methods=["POST"])
def extract():
    url = request.form.get("api_url")
    data = extract_json_response(_cached_apis, url)
    arrays = find_arrays(data)
    return render_template("extract.html", api_url=url, arrays=arrays)


@app.route("/generate-mapping", methods=["POST"])
def generate_mapping():
    global _cached_apis

    api_url = request.form.get("api_url")
    selected_array = request.form.get("selected_array")

    data = extract_json_response(_cached_apis, api_url)

    def find_array(obj, target):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k == target and isinstance(v, list):
                    return v
                sub = find_array(v, target)
                if sub:
                    return sub
        if isinstance(obj, list):
            for item in obj:
                sub = find_array(item, target)
                if sub:
                    return sub
        return None

    array_data = find_array(data, selected_array)
    if not array_data:
        return "Array not found"

    first_obj = array_data[0]
    columns = []

    def walk(o, prefix=""):
        for k, v in o.items():
            path = f"{prefix}/{k}" if prefix else k
            if isinstance(v, dict):
                walk(v, path)
            elif isinstance(v, list):
                if len(v) > 0 and isinstance(v[0], dict):
                    walk(v[0], path)
            else:
                columns.append({
                    "path": f"./{path}",
                    "dataType": "string",
                    "columnName": k
                })

    walk(first_obj)

    mapping = {
        "table": {
            "primaryPath": f"data.{selected_array}[]",
            "columns": columns
        }
    }

    return render_template(
        "mapping_output.html",
        mapping=json.dumps(mapping, indent=2),
        api_url=api_url,
        mode="1",
        keys=json.dumps([selected_array])
    )

@app.route("/generate-mapping-model2", methods=["POST"])
def generate_mapping_model2():
    global _cached_apis

    api_url = request.form.get("api_url")
    selected = request.form.get("selected_object")

    data = extract_json_response(_cached_apis, api_url)
    dot = find_numeric_object_path(data, selected)
    obj = get_by_dotpath(data, dot)

    numeric_key = None
    sample = None
    if isinstance(obj, dict):
        for k in obj:
            if re.fullmatch(r"\d+", str(k)):
                numeric_key = k
                sample = obj[k]
                break

    if sample is None:
        return f"No numeric-key object for {selected}"

    columns = [{
        "path": f"${selected}_id",
        "dataType": "string",
        "columnName": f"{selected}_id"
    }]

    def add(o, prefix):
        for k, v in o.items():
            if isinstance(v, dict):
                add(v, f"{prefix}/{k}")
            elif isinstance(v, list):
                if len(v) > 0 and isinstance(v[0], dict):
                    add(v[0], f"{prefix}/{k}")
            else:
                columns.append({
                    "path": f"./{prefix}/{k}",
                    "dataType": "string",
                    "columnName": k
                })

    add(sample, f"${selected}_id")

    mapping = {
        "table": {
            "primaryPath": f"{dot}{{}}",
            "columns": columns
        }
    }

    return render_template(
        "mapping_output.html",
        mapping=json.dumps(mapping, indent=2),
        api_url=api_url,
        mode="2",
        keys=json.dumps([selected])
    )


@app.route("/generate-mapping-model3", methods=["POST"])
def generate_mapping_model3():
    global _cached_apis

    api_url = request.form.get("api_url")
    selected = request.form.get("selected_object")

    data = extract_json_response(_cached_apis, api_url)

    def find_obj(o, target):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == target and isinstance(v, dict):
                    return v, [k]
                sub, path = find_obj(v, target)
                if sub:
                    return sub, [k] + path
        if isinstance(o, list):
            for item in o:
                sub, path = find_obj(item, target)
                if sub:
                    return sub, path
        return None, None

    obj, path_segments = find_obj(data, selected)
    if obj is None:
        return f"Object {selected} not found"

    primary = ".".join(path_segments)

    columns = []

    def add(o, prefix):
        for k, v in o.items():
            full = f"{prefix}/{k}" if prefix else k
            if isinstance(v, dict):
                add(v, full)
            elif isinstance(v, list):
                if len(v) > 0 and isinstance(v[0], dict):
                    add(v[0], full)
            else:
                columns.append({
                    "path": f"./{full}",
                    "dataType": "string",
                    "columnName": k
                })

    add(obj, "")

    mapping = {
        "table": {
            "primaryPath": f"{primary}{{}}",
            "columns": columns
        }
    }

    return render_template(
        "mapping_output.html",
        mapping=json.dumps(mapping, indent=2),
        api_url=api_url,
        mode="3",
        keys=json.dumps([selected])
    )


@app.route("/save-mapping", methods=["POST"])
def save_mapping():
    global _cached_apis

    api_url = request.form.get("api_url")
    mode = request.form.get("mode")
    keys_raw = request.form.get("keys")
    mapping_raw = request.form.get("mapping")

    if not api_url or not mapping_raw:
        return jsonify({"error": "api_url and mapping are required"}), 400

   
    try:
        keys = json.loads(keys_raw)
    except:
        keys = [keys_raw]

  
    try:
        mapping_obj = json.loads(mapping_raw)
    except:
        mapping_obj = {"raw": mapping_raw}

   
    response_obj = {}
    for a in _cached_apis:
        if a.get("url") == api_url:
            response_obj = a.get("data")
            break

   
    api_id = get_or_create_api(api_url, response_obj)

   
    data_id = save_data_and_get_id(mode, keys, mapping_obj)

   
    create_mapper(api_id, data_id)

    return jsonify({"ok": True, "api_id": api_id, "data_id": data_id})


# @app.route("/extract-model2", methods=["POST"])
# def extract_model2():
#     url = request.form.get("api_url")
#     data = extract_json_response(_cached_apis, url)
#     results = extract_id_objects(data) if data else []
#     max_keys = max((len(r["keys_list"]) for r in results), default=0)
#     return render_template("extract_model2.html", api_url=url, results=results, max_keys=max_keys, arrays=find_arrays(data))


# @app.route("/extract-model3", methods=["POST"])
# def extract_model3():
#     url = request.form.get("api_url")
#     data = extract_json_response(_cached_apis, url)
#     results = extract_objects_model3(data) if data else []
#     return render_template("extract_model3.html", api_url=url, results=results, arrays=find_arrays(data))


@app.route("/extract-model2", methods=["POST"])
def extract_model2():
    url = request.form.get("api_url")
    data = extract_json_response(_cached_apis, url)
    results = extract_id_objects(data) if data else []
    max_keys = max((len(r["keys_list"]) for r in results), default=0)
    return render_template("extract_model2.html", api_url=url, results=results, max_keys=max_keys, arrays=find_arrays(data))


@app.route("/extract-model3", methods=["POST"])
def extract_model3():
    url = request.form.get("api_url")
    data = extract_json_response(_cached_apis, url)
    results = extract_objects_model3(data) if data else []
    return render_template("extract_model3.html", api_url=url, results=results, arrays=find_arrays(data))



@app.route("/saved-apis")
def saved_apis():
    tag_filter = request.args.get('tag')
    url_filter = request.args.get('url', '').strip()
    
    with db_session() as session:
        # Get all tags with counts for the filter
        all_tags_with_counts = session.query(
            Tag,
            func.count(API.id).label('count')
        ).outerjoin(
            API.tags
        ).group_by(Tag.id).order_by(Tag.name).all()
        
        # Get all tags for the dropdown (simple list of tag objects)
        all_tags = session.query(Tag).order_by(Tag.name).all()
        
        # Debug: Print number of tags
        print(f"DEBUG: Found {len(all_tags)} total tags")
        for tag in all_tags:
            print(f"- {tag.id}: {tag.name}")
            
        # Ensure we have all tags for the dropdown
        all_tags = session.query(Tag).order_by(Tag.name).all()
        
        # Start with base query
        query = session.query(API)
        
        # Apply tag filter if specified
        if tag_filter:
            query = query.join(API.tags).filter(Tag.name == tag_filter)
        
        # Apply URL filter if specified
        if url_filter:
            query = query.filter(API.api.ilike(f'%{url_filter}%'))
        
        # Get filtered APIs with their tags
        apis = []
        for api in query.all():
            api_dict = {
                'id': api.id,
                'api': api.api,
                'tag': api.tags[0] if api.tags else None,  # Single tag per API
                'tags': [tag.name for tag in api.tags]  # For backward compatibility
            }
            apis.append(api_dict)
        
        # Get total count of all APIs
        total_apis = session.query(API).count()
        
        return render_template(
            'saved_apis.html', 
            apis=apis,
            tags=all_tags,  # Pass all tags for dropdowns
            all_tags_with_counts=all_tags_with_counts,
            total_apis=total_apis,
            current_tag=tag_filter,
            current_url_filter=url_filter
        )


@app.route("/view-saved-api/<int:api_id>")
def view_saved_api(api_id):
    with db_session() as session:
        api = session.query(API).filter(API.id == api_id).first()
        if not api:
            return "API not found", 404

       
        mapper_rows = session.query(Mapper).filter(Mapper.api_id == api_id).all()
        data_ids = [m.data_id for m in mapper_rows]

    
        data_rows = session.query(Data).filter(Data.id.in_(data_ids)).all()

    return render_template(
        "view_api_combined.html",
        api=api,
        data_rows=data_rows
    )
@app.route("/get-mapping/<int:data_id>")
def get_mapping(data_id):
    with db_session() as session:
        d = session.query(Data).filter(Data.id == data_id).first()
        if not d:
            return jsonify({"error": "Not found"}), 404

        return jsonify({
            "mode": d.mode,
            "keys": json.loads(d.keys),
            "mapping": json.loads(d.mapping)
        })

@app.route("/delete-api/<int:api_id>", methods=["GET"])
def delete_api(api_id):
    with db_session() as session:
       
        api = session.query(API).filter(API.id == api_id).first()
        if not api:
            return "API not found", 404

       
        mappings = session.query(Mapper).filter(Mapper.api_id == api_id).all()

        
        data_ids = [m.data_id for m in mappings]
       
        session.query(Mapper).filter(Mapper.api_id == api_id).delete()

        if data_ids:
            session.query(Data).filter(Data.id.in_(data_ids)).delete(synchronize_session=False)
       
        session.delete(api)

        session.commit()

    return redirect(url_for("saved_apis"))

@app.route("/results")
def results_page():
    apis = [a for a in _cached_apis if a.get("data")]
    return render_template("results.html", apis=apis)


@app.route('/add-tags', methods=['GET', 'POST'])
def add_tags():
    with db_session() as session:
        # Get all tags with counts for the dropdown
        all_tags = session.query(
            Tag,
            func.count(API.id).label('count')
        ).join(
            API.tags
        ).group_by(Tag.id).all()
        if request.method == 'POST':
            api_url = request.form.get('api_url')
            tag_name = request.form.get('tag_name')
            
            if not api_url or not tag_name:
                flash('Both API URL and tag are required', 'error')
                return render_template('add_tags.html', all_tags=all_tags)
                
            try:
                # Check if API already exists
                api = session.query(API).filter(API.api == api_url).first()
                
                if not api:
                    # Create new API if it doesn't exist
                    api = API(api=api_url, response='{}')
                    session.add(api)
                    session.commit()
                    session.refresh(api)
                
                # Check if tag exists
                tag = session.query(Tag).filter(Tag.name == tag_name).first()
                if not tag:
                    tag = Tag(name=tag_name)
                    session.add(tag)
                    session.commit()
                    session.refresh(tag)
                
                # Clear existing tags and add the new one
                api.tags = [tag]
                session.commit()
                
                flash(f'Successfully added tag "{tag_name}" to API', 'success')
                return redirect(url_for('add_tags'))
                
            except Exception as e:
                session.rollback()
                flash(f'Error adding tag: {str(e)}', 'error')
                return render_template('add_tags.html', all_tags=all_tags)
        
        # For GET requests
        return render_template('add_tags.html', all_tags=all_tags)

@app.route('/api/<int:api_id>/tags', methods=['DELETE'])
def delete_tag(api_id):
    tag_name = request.form.get('tag_name')
    with db_session() as session:
        remove_tag_from_api(session, api_id, tag_name)
        return jsonify({'status': 'success'})

@app.route('/api/tags')
def list_tags():
    with db_session() as session:
        tags = [tag.name for tag in get_all_tags(session)]
        return jsonify(tags)

@app.route('/api/tags/<tag_name>')
def get_tagged_apis(tag_name):
    with db_session() as session:
        apis = get_apis_by_tag(session, tag_name)
        return jsonify([{'id': api.id, 'api': api.api} for api in apis])

@app.route('/update-api-tag/<int:api_id>', methods=['POST'])
def update_api_tag(api_id):
    with db_session() as session:
        tag_id = request.form.get('tag_id')
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        if not tag_id:
            error_msg = 'Please select a tag'
            if is_ajax:
                return jsonify({'success': False, 'error': error_msg})
            flash(error_msg, 'error')
            return redirect(url_for('saved_apis'))
        
        try:
            # Ensure tag_id is an integer
            tag_id = int(tag_id)
            
            api = session.query(API).get(api_id)
            if not api:
                error_msg = 'API not found'
                if is_ajax:
                    return jsonify({'success': False, 'error': error_msg})
                flash(error_msg, 'error')
                return redirect(url_for('saved_apis'))
            
            # Check if tag exists
            tag = session.query(Tag).get(tag_id)
            if not tag:
                error_msg = 'Selected tag not found'
                if is_ajax:
                    return jsonify({'success': False, 'error': error_msg})
                flash(error_msg, 'error')
                return redirect(url_for('saved_apis'))
            
            # Clear existing tags and add the new one
            api.tags = [tag]
            session.commit()
            
            if is_ajax:
                return jsonify({
                    'success': True, 
                    'message': 'Tag updated successfully',
                    'tag': {'id': tag.id, 'name': tag.name}
                })
            
            flash('Tag updated successfully', 'success')
            return redirect(url_for('saved_apis'))
            
        except ValueError:
            error_msg = 'Invalid tag ID'
            if is_ajax:
                return jsonify({'success': False, 'error': error_msg})
            flash(error_msg, 'error')
            return redirect(url_for('saved_apis'))
        except Exception as e:
            session.rollback()
            error_msg = f'Error updating tag: {str(e)}'
            if is_ajax:
                return jsonify({'success': False, 'error': error_msg})
            flash(error_msg, 'error')
            return redirect(url_for('saved_apis'))
            return redirect(url_for('saved_apis'))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
