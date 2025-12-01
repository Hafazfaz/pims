
@api.route('/files', methods=['GET'])
@jwt_required()
@permission_required('read_document')
def get_files():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # Search functionality
        search_query = request.args.get('search')
        
        base_query = """
            SELECT f.id, f.file_number, f.filename, f.file_category, d.name as department_name, 
                   u.username as uploader_name, f.created_at, f.status
            FROM files f
            JOIN departments d ON f.department_id = d.id
            JOIN users u ON f.uploader_id = u.id
        """
        
        if search_query:
            base_query += " WHERE f.filename LIKE %s OR f.file_number LIKE %s"
            params = (f"%{search_query}%", f"%{search_query}%")
            cursor.execute(base_query, params)
        else:
            cursor.execute(base_query)
            
        files = cursor.fetchall()
        return jsonify(files)
    except mysql.connector.Error as err:
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()
