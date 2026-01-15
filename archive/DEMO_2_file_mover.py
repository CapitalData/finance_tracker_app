# Callback to update the file checklist based on the source folder
@app.callback(
    Output('file-checklist', 'children'),
    Input('source-path', 'value')
)
def update_file_checklist(source_path):
    if source_path and os.path.isdir(source_path):
        files = glob.glob(os.path.join(source_path, "*"))
        file_options = []
        for file in files:
            if os.path.isfile(file):
                file_options.append(
                    dcc.Checklist(
                        id=f"file-checklist-{os.path.basename(file)}",
                        options=[{'label': os.path.basename(file), 'value': file}],
                        value=[],  # No default selections
                        inline=True
                    )
                )
        return file_options
    return html.Div("Please enter a valid source path.")

# Callback to move files when the button is clicked
@app.callback(
    Output('feedback', 'children'),
    Input('move-button', 'n_clicks'),
    [State('destination-path', 'value'),
     State('file-checklist', 'children')]
)
def move_files(n_clicks, destination_path, file_checklist):
    if n_clicks:
        if destination_path and os.path.isdir(destination_path) and file_checklist:
            selected_files = []
            for checklist in file_checklist:
                # Accessing the checklist's value property
                selected_files.extend(checklist['props'].get('value', []))
            if selected_files:
                messages = []
                for selected_file in selected_files:
                    try:
                        shutil.move(selected_file, os.path.join(destination_path, os.path.basename(selected_file)))
                        messages.append(f"Moved {selected_file} to {destination_path}")
                    except Exception as e:
                        messages.append(f"Error moving {selected_file}: {e}")
                return html.Div(messages)
            else:
                return "No files selected for moving."
        else:
            return "Invalid destination path or no files to move."
    return ""