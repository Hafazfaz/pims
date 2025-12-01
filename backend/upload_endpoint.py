
@api.route('/files', methods=['POST'])
@jwt_required()
@permission_required('create_document')
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    data = request.form
    file_category = data.get('file_category')
    department_id = data.get('department_id')
    sensitivity = data.get('sensitivity')
    expires_at = data.get('expires_at')
    tags_str = data.get('tags')

    if not file_category or not department_id or not sensitivity:
        return jsonify({'error': 'File category, department, and sensitivity are required'}), 400

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    filepath = None
    try:
        current_username = get_jwt_identity()
        cursor.execute("SELECT id FROM users WHERE username = %s", (current_username,))
        user = cursor.fetchone()
        if not user:
            return jsonify({'error': 'Uploader user not found'}), 404
        uploader_id = user['id']

        cursor.execute("SELECT code FROM departments WHERE id = %s", (department_id,))
        department_data = cursor.fetchone()
        if not department_data:
            return jsonify({'error': 'Department not found'}), 400
        department_code = department_data['code']

        # Generate file number
        cursor.execute("SELECT COUNT(*) as count FROM files WHERE department_id = %s", (department_id,))
        file_count = cursor.fetchone()['count']
        file_number = f"{department_code}-{file_count + 1}"

        # Save the file
        original_filename = file.filename
        safe_filename = secure_filename(original_filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], safe_filename)
        file.save(filepath)

        # Insert into database
        cursor.execute("INSERT INTO files (file_number, filename, filepath, file_category, department_id, uploader_id, sensitivity, expires_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", 
                       (file_number, original_filename, filepath, file_category, department_id, uploader_id, sensitivity, expires_at))
        file_id = cursor.lastrowid
        
        # Insert tags into file_tags table
        if tags_str:
            tags = [tag.strip() for tag in tags_str.split(',') if tag.strip()]
            for tag in tags:
                cursor.execute("INSERT INTO file_tags (file_id, tag) VALUES (%s, %s)", (file_id, tag))

        # Log file creation in file_history
        log_file_history(file_id, uploader_id, 'created', f'File {original_filename} uploaded.')
        
        conn.commit()
        return jsonify({'message': 'File uploaded successfully', 'file_id': file_id, 'file_number': file_number}), 201

    except mysql.connector.Error as err:
        conn.rollback()
        if filepath and os.path.exists(filepath):
            os.remove(filepath)
        return jsonify({'error': str(err)}), 500
    except Exception as e:
        conn.rollback()
        if filepath and os.path.exists(filepath):
            os.remove(filepath)
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()
