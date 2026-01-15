"""
Admin dashboard for user management
Accessible only to users with admin privileges
"""

import dash
from dash import dcc, html, Input, Output, State, no_update, dash_table
import finance_db
import pandas as pd

# Create admin app
admin_app = dash.Dash(__name__, url_base_pathname='/admin/')

admin_app.layout = html.Div([
    html.H1("🔐 User Management Dashboard", style={
        "textAlign": "center",
        "color": "#2c3e50",
        "marginBottom": "30px"
    }),
    
    # Session store
    dcc.Store(id='admin-session-store', storage_type='session'),
    
    # Login section
    html.Div(id='admin-login-container', children=[
        html.Div([
            html.H2("Admin Login"),
            dcc.Input(
                id='admin-username',
                type='text',
                placeholder='Admin username',
                style={"width": "100%", "padding": "10px", "marginBottom": "10px"}
            ),
            dcc.Input(
                id='admin-password',
                type='password',
                placeholder='Admin password',
                style={"width": "100%", "padding": "10px", "marginBottom": "15px"}
            ),
            html.Button("Login", id="admin-login-btn", n_clicks=0, style={
                "width": "100%",
                "padding": "12px",
                "backgroundColor": "#3498db",
                "color": "white",
                "border": "none",
                "borderRadius": "5px",
                "fontSize": "16px",
                "cursor": "pointer"
            }),
            html.Div(id='admin-login-message', style={
                "marginTop": "15px",
                "textAlign": "center",
                "fontWeight": "bold"
            })
        ], style={
            "maxWidth": "400px",
            "margin": "100px auto",
            "padding": "40px",
            "backgroundColor": "#ecf0f1",
            "borderRadius": "10px",
            "boxShadow": "0 4px 6px rgba(0,0,0,0.1)"
        })
    ]),
    
    # Admin panel (hidden until logged in)
    html.Div(id='admin-panel-container', style={'display': 'none'}, children=[
        html.Div([
            html.H3(id='admin-welcome-text'),
            html.Button("🚪 Logout", id="admin-logout-btn", n_clicks=0, style={
                "padding": "10px 20px",
                "backgroundColor": "#e74c3c",
                "color": "white",
                "border": "none",
                "borderRadius": "5px",
                "cursor": "pointer",
                "marginBottom": "20px"
            }),
            html.Button("🔄 Refresh List", id="refresh-users-btn", n_clicks=0, style={
                "padding": "10px 20px",
                "backgroundColor": "#3498db",
                "color": "white",
                "border": "none",
                "borderRadius": "5px",
                "cursor": "pointer",
                "marginBottom": "20px",
                "marginLeft": "10px"
            })
        ]),
        
        # User statistics
        html.Div(id='user-stats', style={
            "backgroundColor": "#ecf0f1",
            "padding": "20px",
            "borderRadius": "10px",
            "marginBottom": "30px"
        }),
        
        # User list table
        html.Div([
            html.H3("👥 User Accounts"),
            html.Div(id='users-table-container')
        ]),
        
        # User actions section
        html.Div([
            html.H3("⚙️ User Actions", style={"marginTop": "30px"}),
            html.Div([
                dcc.Input(
                    id='action-user-id',
                    type='number',
                    placeholder='User ID',
                    style={"padding": "10px", "marginRight": "10px"}
                ),
                html.Button("Disable User", id="disable-user-btn", n_clicks=0, style={
                    "padding": "10px 20px",
                    "backgroundColor": "#e67e22",
                    "color": "white",
                    "border": "none",
                    "borderRadius": "5px",
                    "cursor": "pointer",
                    "marginRight": "10px"
                }),
                html.Button("Enable User", id="enable-user-btn", n_clicks=0, style={
                    "padding": "10px 20px",
                    "backgroundColor": "#27ae60",
                    "color": "white",
                    "border": "none",
                    "borderRadius": "5px",
                    "cursor": "pointer",
                    "marginRight": "10px"
                }),
            ], style={"marginBottom": "15px"}),
            
            html.Div([
                dcc.Input(
                    id='reset-password-user-id',
                    type='number',
                    placeholder='User ID',
                    style={"padding": "10px", "marginRight": "10px"}
                ),
                dcc.Input(
                    id='new-password-admin',
                    type='password',
                    placeholder='New password',
                    style={"padding": "10px", "marginRight": "10px"}
                ),
                html.Button("Reset Password", id="reset-password-btn", n_clicks=0, style={
                    "padding": "10px 20px",
                    "backgroundColor": "#8e44ad",
                    "color": "white",
                    "border": "none",
                    "borderRadius": "5px",
                    "cursor": "pointer"
                }),
            ]),
            
            html.Div(id='admin-action-message', style={
                "marginTop": "15px",
                "padding": "10px",
                "borderRadius": "5px",
                "fontWeight": "bold"
            })
        ])
    ], style={"padding": "30px", "maxWidth": "1200px", "margin": "0 auto"})
], style={"fontFamily": "Arial, sans-serif", "minHeight": "100vh", "backgroundColor": "#f8f9fa"})


# Admin login callback
@admin_app.callback(
    [Output('admin-session-store', 'data'),
     Output('admin-login-message', 'children'),
     Output('admin-login-message', 'style')],
    [Input('admin-login-btn', 'n_clicks')],
    [State('admin-username', 'value'),
     State('admin-password', 'value')]
)
def admin_login(n_clicks, username, password):
    if n_clicks == 0:
        return None, '', {}
    
    if not username or not password:
        return None, 'Please enter credentials', {"color": "red"}
    
    # Authenticate
    success, message, user_dict = finance_db.authenticate_user(username, password)
    
    if success and user_dict.get('is_admin'):
        session_id = finance_db.create_session(user_dict['id'])
        return {
            'session_id': session_id,
            'user_id': user_dict['id'],
            'username': user_dict['username']
        }, 'Login successful!', {"color": "green"}
    elif success:
        return None, 'Access denied. Admin privileges required.', {"color": "red"}
    else:
        return None, message, {"color": "red"}


# Show/hide admin panel based on auth
@admin_app.callback(
    [Output('admin-login-container', 'style'),
     Output('admin-panel-container', 'style'),
     Output('admin-welcome-text', 'children')],
    [Input('admin-session-store', 'data'),
     Input('admin-logout-btn', 'n_clicks')]
)
def control_admin_access(session_data, logout_clicks):
    from dash import ctx
    
    button_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None
    
    # Handle logout
    if button_id == 'admin-logout-btn' and logout_clicks > 0:
        if session_data and 'session_id' in session_data:
            finance_db.delete_session(session_data['session_id'])
        return {'display': 'block'}, {'display': 'none'}, ''
    
    # Check auth
    if not session_data or 'session_id' not in session_data:
        return {'display': 'block'}, {'display': 'none'}, ''
    
    # Validate session and check admin
    valid, user_dict = finance_db.validate_session(session_data['session_id'])
    
    if valid and user_dict.get('is_admin'):
        welcome = f"Welcome, Admin {user_dict['username']}!"
        return {'display': 'none'}, {'display': 'block'}, welcome
    else:
        return {'display': 'block'}, {'display': 'none'}, ''


# Update user list
@admin_app.callback(
    [Output('users-table-container', 'children'),
     Output('user-stats', 'children')],
    [Input('admin-session-store', 'data'),
     Input('refresh-users-btn', 'n_clicks'),
     Input('disable-user-btn', 'n_clicks'),
     Input('enable-user-btn', 'n_clicks'),
     Input('reset-password-btn', 'n_clicks')]
)
def update_user_list(session_data, refresh_clicks, disable_clicks, enable_clicks, reset_clicks):
    if not session_data or 'session_id' not in session_data:
        return "Not authenticated", ""
    
    # Validate session
    valid, user_dict = finance_db.validate_session(session_data['session_id'])
    
    if not valid or not user_dict.get('is_admin'):
        return "Access denied", ""
    
    # Get all users
    users = finance_db.list_all_users()
    
    if not users:
        return "No users found", ""
    
    # Create DataFrame
    df = pd.DataFrame(users)
    
    # Format dates
    df['created_at'] = pd.to_datetime(df['created_at']).dt.strftime('%Y-%m-%d %H:%M')
    df['last_login'] = pd.to_datetime(df['last_login'], errors='coerce').dt.strftime('%Y-%m-%d %H:%M')
    df['last_login'] = df['last_login'].fillna('Never')
    
    # Create table
    table = dash_table.DataTable(
        data=df.to_dict('records'),
        columns=[
            {"name": "ID", "id": "id"},
            {"name": "Username", "id": "username"},
            {"name": "Email", "id": "email"},
            {"name": "Admin", "id": "is_admin"},
            {"name": "Active", "id": "is_active"},
            {"name": "Created", "id": "created_at"},
            {"name": "Last Login", "id": "last_login"}
        ],
        style_table={'overflowX': 'auto'},
        style_cell={
            'textAlign': 'left',
            'padding': '10px',
            'fontSize': '14px'
        },
        style_header={
            'backgroundColor': '#3498db',
            'color': 'white',
            'fontWeight': 'bold'
        },
        style_data_conditional=[
            {
                'if': {'filter_query': '{is_active} = false'},
                'backgroundColor': '#ffdddd'
            },
            {
                'if': {'filter_query': '{is_admin} = true'},
                'backgroundColor': '#ddffdd'
            }
        ]
    )
    
    # Calculate statistics
    total_users = len(users)
    active_users = sum(1 for u in users if u['is_active'])
    admin_users = sum(1 for u in users if u['is_admin'])
    
    stats = html.Div([
        html.Div([
            html.H4("📊 User Statistics"),
            html.P(f"Total Users: {total_users}", style={"fontSize": "16px", "margin": "5px 0"}),
            html.P(f"Active Users: {active_users}", style={"fontSize": "16px", "margin": "5px 0", "color": "green"}),
            html.P(f"Inactive Users: {total_users - active_users}", style={"fontSize": "16px", "margin": "5px 0", "color": "red"}),
            html.P(f"Admin Users: {admin_users}", style={"fontSize": "16px", "margin": "5px 0", "color": "blue"})
        ])
    ])
    
    return table, stats


# User action callbacks
@admin_app.callback(
    [Output('admin-action-message', 'children'),
     Output('admin-action-message', 'style')],
    [Input('disable-user-btn', 'n_clicks'),
     Input('enable-user-btn', 'n_clicks'),
     Input('reset-password-btn', 'n_clicks')],
    [State('admin-session-store', 'data'),
     State('action-user-id', 'value'),
     State('reset-password-user-id', 'value'),
     State('new-password-admin', 'value')]
)
def perform_user_action(disable_clicks, enable_clicks, reset_clicks, 
                       session_data, user_id, reset_user_id, new_password):
    from dash import ctx
    
    if not session_data or 'session_id' not in session_data:
        return "Not authenticated", {"backgroundColor": "#ffdddd", "color": "red"}
    
    # Validate admin session
    valid, user_dict = finance_db.validate_session(session_data['session_id'])
    if not valid or not user_dict.get('is_admin'):
        return "Access denied", {"backgroundColor": "#ffdddd", "color": "red"}
    
    button_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None
    
    if button_id == 'disable-user-btn' and disable_clicks > 0:
        if not user_id:
            return "Please enter User ID", {"backgroundColor": "#ffdddd", "color": "red"}
        success, message = finance_db.toggle_user_status(user_id, False)
        color = "green" if success else "red"
        bg = "#ddffdd" if success else "#ffdddd"
        return message, {"backgroundColor": bg, "color": color}
    
    elif button_id == 'enable-user-btn' and enable_clicks > 0:
        if not user_id:
            return "Please enter User ID", {"backgroundColor": "#ffdddd", "color": "red"}
        success, message = finance_db.toggle_user_status(user_id, True)
        color = "green" if success else "red"
        bg = "#ddffdd" if success else "#ffdddd"
        return message, {"backgroundColor": bg, "color": color"}
    
    elif button_id == 'reset-password-btn' and reset_clicks > 0:
        if not reset_user_id or not new_password:
            return "Please enter User ID and new password", {"backgroundColor": "#ffdddd", "color": "red"}
        success, message = finance_db.admin_reset_password(reset_user_id, new_password)
        color = "green" if success else "red"
        bg = "#ddffdd" if success else "#ffdddd"
        return message, {"backgroundColor": bg, "color": color"}
    
    return "", {}


if __name__ == '__main__':
    # Initialize database
    finance_db.init_database()
    admin_app.run_server(debug=True, port=8052)
