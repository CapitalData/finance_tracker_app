"""
Authentication callbacks for finance tracker dashboard
Handles login, registration, password changes, and session management
"""

from dash import Input, Output, State, no_update, dcc, html
import finance_db


def register_auth_callbacks(app):
    """Register all authentication-related callbacks"""
    
    # Form switcher callback
    @app.callback(
        [Output('login-form', 'style'),
         Output('register-form', 'style'),
         Output('switch-to-login', 'style'),
         Output('switch-to-register', 'style')],
        [Input('switch-to-login', 'n_clicks'),
         Input('switch-to-register', 'n_clicks')]
    )
    def switch_form(login_clicks, register_clicks):
        """Switch between login and registration forms"""
        from dash import ctx
        
        button_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else 'switch-to-login'
        
        login_active_style = {
            "padding": "10px 20px",
            "fontSize": "14px",
            "fontWeight": "bold",
            "backgroundColor": "#4A90E2",
            "color": "white",
            "border": "none",
            "borderRadius": "5px 0 0 5px",
            "cursor": "pointer",
            "flex": "1"
        }
        
        login_inactive_style = login_active_style.copy()
        login_inactive_style["backgroundColor"] = "#6c757d"
        
        register_active_style = {
            "padding": "10px 20px",
            "fontSize": "14px",
            "fontWeight": "bold",
            "backgroundColor": "#4A90E2",
            "color": "white",
            "border": "none",
            "borderRadius": "0 5px 5px 0",
            "cursor": "pointer",
            "flex": "1"
        }
        
        register_inactive_style = register_active_style.copy()
        register_inactive_style["backgroundColor"] = "#6c757d"
        
        if button_id == 'switch-to-register':
            return ({'display': 'none'}, {'display': 'block'}, 
                    login_inactive_style, register_active_style)
        else:
            return ({'display': 'block'}, {'display': 'none'},
                    login_active_style, register_inactive_style)
    
    
    # Registration callback
    @app.callback(
        [Output('auth-message', 'children'),
         Output('auth-message', 'style'),
         Output('register-username-input', 'value'),
         Output('register-email-input', 'value'),
         Output('register-password-input', 'value'),
         Output('register-password-confirm-input', 'value')],
        [Input('register-submit-btn', 'n_clicks')],
        [State('register-username-input', 'value'),
         State('register-email-input', 'value'),
         State('register-password-input', 'value'),
         State('register-password-confirm-input', 'value')]
    )
    def register_user(n_clicks, username, email, password, password_confirm):
        """Handle user registration"""
        if n_clicks == 0:
            return '', {"marginTop": "20px", "textAlign": "center", "fontWeight": "bold", 
                       "textShadow": "1px 1px 2px rgba(0,0,0,0.8)", "minHeight": "24px"}, '', '', '', ''
        
        # Validate inputs
        if not username or not email or not password or not password_confirm:
            style = {"marginTop": "20px", "textAlign": "center", "fontWeight": "bold", 
                    "textShadow": "1px 1px 2px rgba(0,0,0,0.8)", "color": "#ff6b6b"}
            return 'Please fill in all fields', style, no_update, no_update, '', ''
        
        if password != password_confirm:
            style = {"marginTop": "20px", "textAlign": "center", "fontWeight": "bold", 
                    "textShadow": "1px 1px 2px rgba(0,0,0,0.8)", "color": "#ff6b6b"}
            return 'Passwords do not match', style, no_update, no_update, '', ''
        
        # Create user in database
        success, message, user_id = finance_db.create_user(username, email, password)
        
        if success:
            style = {"marginTop": "20px", "textAlign": "center", "fontWeight": "bold", 
                    "textShadow": "1px 1px 2px rgba(0,0,0,0.8)", "color": "#28a745"}
            return f'{message}. Please login.', style, '', '', '', ''
        else:
            style = {"marginTop": "20px", "textAlign": "center", "fontWeight": "bold", 
                    "textShadow": "1px 1px 2px rgba(0,0,0,0.8)", "color": "#ff6b6b"}
            return message, style, no_update, no_update, '', ''
    
    
    # Login callback
    @app.callback(
        [Output('user-session-store', 'data'),
         Output('auth-message', 'children', allow_duplicate=True),
         Output('auth-message', 'style', allow_duplicate=True),
         Output('login-username-input', 'value'),
         Output('login-password-input', 'value')],
        [Input('login-submit-btn', 'n_clicks')],
        [State('login-username-input', 'value'),
         State('login-password-input', 'value')],
        prevent_initial_call=True
    )
    def login_user(n_clicks, username, password):
        """Handle user login"""
        if n_clicks == 0:
            return None, '', {"marginTop": "20px", "textAlign": "center", "fontWeight": "bold", 
                             "textShadow": "1px 1px 2px rgba(0,0,0,0.8)", "minHeight": "24px"}, '', ''
        
        if not username or not password:
            style = {"marginTop": "20px", "textAlign": "center", "fontWeight": "bold", 
                    "textShadow": "1px 1px 2px rgba(0,0,0,0.8)", "color": "#ff6b6b"}
            return None, 'Please enter username and password', style, no_update, ''
        
        # Authenticate user
        success, message, user_dict = finance_db.authenticate_user(username, password)
        
        if success:
            # Create session
            session_id = finance_db.create_session(user_dict['id'])
            
            if session_id:
                # Store session in browser
                session_data = {
                    'session_id': session_id,
                    'user_id': user_dict['id'],
                    'username': user_dict['username'],
                    'email': user_dict['email'],
                    'is_admin': user_dict['is_admin']
                }
                
                style = {"marginTop": "20px", "textAlign": "center", "fontWeight": "bold", 
                        "textShadow": "1px 1px 2px rgba(0,0,0,0.8)", "color": "#28a745"}
                return session_data, '✅ Login successful!', style, '', ''
            else:
                style = {"marginTop": "20px", "textAlign": "center", "fontWeight": "bold", 
                        "textShadow": "1px 1px 2px rgba(0,0,0,0.8)", "color": "#ff6b6b"}
                return None, 'Error creating session', style, no_update, ''
        else:
            style = {"marginTop": "20px", "textAlign": "center", "fontWeight": "bold", 
                    "textShadow": "1px 1px 2px rgba(0,0,0,0.8)", "color": "#ff6b6b"}
            return None, message, style, no_update, ''
    
    
    # Main Quick Links access control callback
    @app.callback(
        [Output('quicklinks-auth-container', 'style'),
         Output('quicklinks-content-container', 'style'),
         Output('quicklinks-user-profile', 'children')],
        [Input('user-session-store', 'data'),
         Input('logout-btn', 'n_clicks')],
        prevent_initial_call=False
    )
    def control_quicklinks_access(session_data, logout_clicks):
        """Control access to Quick Links content based on authentication"""
        from dash import ctx
        import dash.html as html
        
        print(f"DEBUG control_quicklinks_access: session_data={session_data}, logout_clicks={logout_clicks}")
        
        button_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None
        print(f"DEBUG button_id: {button_id}")
        
        # Handle logout
        if button_id == 'logout-btn' and logout_clicks and logout_clicks > 0:
            if session_data and 'session_id' in session_data:
                finance_db.delete_session(session_data['session_id'])
            
            # Show auth form
            print("DEBUG: Logging out, showing auth form")
            return {'display': 'block'}, {'display': 'none'}, ''
        
        # Check if user is authenticated
        if not session_data or 'session_id' not in session_data:
            # Not authenticated - show login form
            print("DEBUG: No session, showing auth form")
            return {'display': 'block'}, {'display': 'none'}, ''
        
        # Validate session
        valid, user_dict = finance_db.validate_session(session_data['session_id'])
        print(f"DEBUG: Session validation: valid={valid}, user_dict={user_dict}")
        
        if valid:
            # Authenticated - show content
            # Import here to avoid circular dependency
            user_profile = html.Div([
                html.Div([
                    # User info header
                    html.Div([
                        html.H3(f"👤 Welcome, {user_dict['username']}!", style={
                            "color": "white",
                            "margin": "0",
                            "textShadow": "2px 2px 4px rgba(0,0,0,0.8)"
                        }),
                        html.P(f"📧 {user_dict['email']}", style={
                            "color": "rgba(255,255,255,0.8)",
                            "margin": "5px 0",
                            "textShadow": "1px 1px 3px rgba(0,0,0,0.8)"
                        }),
                        html.P(f"🔐 Last login: {user_dict.get('last_login', 'N/A')[:16] if user_dict.get('last_login') else 'First time'}", style={
                            "color": "rgba(255,255,255,0.7)",
                            "margin": "5px 0",
                            "textShadow": "1px 1px 3px rgba(0,0,0,0.8)",
                            "fontSize": "14px"
                        })
                    ], style={
                        "backgroundColor": "rgba(255,255,255,0.1)",
                        "padding": "20px",
                        "borderRadius": "10px",
                        "marginBottom": "20px"
                    }),
                    
                    # Account actions
                    html.Div([
                        html.Button("🔄 Change Password", id="show-password-change-btn", n_clicks=0, style={
                            "padding": "10px 20px",
                            "fontSize": "14px",
                            "fontWeight": "bold",
                            "backgroundColor": "#4A90E2",
                            "color": "white",
                            "border": "none",
                            "borderRadius": "5px",
                            "cursor": "pointer",
                            "marginRight": "10px"
                        }),
                        html.Button("🚪 Logout", id="logout-btn", n_clicks=0, style={
                            "padding": "10px 20px",
                            "fontSize": "14px",
                            "fontWeight": "bold",
                            "backgroundColor": "#dc3545",
                            "color": "white",
                            "border": "none",
                            "borderRadius": "5px",
                            "cursor": "pointer"
                        })
                    ], style={"marginBottom": "20px"}),
                    
                    # Password change form (hidden by default)
                    html.Div(id='password-change-form', style={'display': 'none'}, children=[
                        html.H4("Change Password", style={"color": "white", "textShadow": "2px 2px 4px rgba(0,0,0,0.8)"}),
                        html.Div([
                            dcc.Input(
                                id='current-password-input',
                                type='password',
                                placeholder='Current password',
                                style={
                                    "width": "100%",
                                    "padding": "10px",
                                    "fontSize": "14px",
                                    "borderRadius": "5px",
                                    "border": "2px solid #ccc",
                                    "marginBottom": "10px",
                                    "boxSizing": "border-box"
                                }
                            ),
                            dcc.Input(
                                id='new-password-input',
                                type='password',
                                placeholder='New password (min 6 characters)',
                                style={
                                    "width": "100%",
                                    "padding": "10px",
                                    "fontSize": "14px",
                                    "borderRadius": "5px",
                                    "border": "2px solid #ccc",
                                    "marginBottom": "10px",
                                    "boxSizing": "border-box"
                                }
                            ),
                            dcc.Input(
                                id='confirm-new-password-input',
                                type='password',
                                placeholder='Confirm new password',
                                style={
                                    "width": "100%",
                                    "padding": "10px",
                                    "fontSize": "14px",
                                    "borderRadius": "5px",
                                    "border": "2px solid #ccc",
                                    "marginBottom": "15px",
                                    "boxSizing": "border-box"
                                }
                            ),
                            html.Button("Update Password", id="update-password-btn", n_clicks=0, style={
                                "padding": "10px 20px",
                                "fontSize": "14px",
                                "fontWeight": "bold",
                                "backgroundColor": "#28a745",
                                "color": "white",
                                "border": "none",
                                "borderRadius": "5px",
                                "cursor": "pointer"
                            }),
                            html.Div(id='password-change-message', style={
                                "marginTop": "10px",
                                "textAlign": "center",
                                "fontWeight": "bold"
                            })
                        ])
                    ])
                    
                ], style={
                    "backgroundColor": "rgba(0,0,0,0.6)",
                    "padding": "30px",
                    "borderRadius": "10px",
                    "maxWidth": "500px",
                    "margin": "20px auto",
                    "border": "2px solid rgba(255,255,255,0.3)"
                })
            ])
            
            print("DEBUG: Returning CONTENT VISIBLE - auth:none, content:block")
            return {'display': 'none'}, {'display': 'block'}, user_profile
        else:
            # Session invalid - show login form
            print("DEBUG: Session invalid, showing auth form")
            return {'display': 'block'}, {'display': 'none'}, ''
    
    
    # Password change form toggle
    @app.callback(
        Output('password-change-form', 'style'),
        [Input('show-password-change-btn', 'n_clicks')],
        [State('password-change-form', 'style')]
    )
    def toggle_password_form(n_clicks, current_style):
        """Toggle password change form visibility"""
        if n_clicks == 0:
            return {'display': 'none'}
        
        if current_style.get('display') == 'none':
            return {'display': 'block', 'marginTop': '20px', 
                   'backgroundColor': 'rgba(255,255,255,0.1)', 
                   'padding': '20px', 'borderRadius': '10px'}
        else:
            return {'display': 'none'}
    
    
    # Password change callback
    @app.callback(
        [Output('password-change-message', 'children'),
         Output('password-change-message', 'style'),
         Output('current-password-input', 'value'),
         Output('new-password-input', 'value'),
         Output('confirm-new-password-input', 'value')],
        [Input('update-password-btn', 'n_clicks')],
        [State('user-session-store', 'data'),
         State('current-password-input', 'value'),
         State('new-password-input', 'value'),
         State('confirm-new-password-input', 'value')]
    )
    def change_password(n_clicks, session_data, current_pass, new_pass, confirm_pass):
        """Handle password change"""
        if n_clicks == 0:
            return '', {"marginTop": "10px", "textAlign": "center", "fontWeight": "bold"}, '', '', ''
        
        if not session_data or 'user_id' not in session_data:
            style = {"marginTop": "10px", "textAlign": "center", "fontWeight": "bold", "color": "#ff6b6b"}
            return 'Not authenticated', style, '', '', ''
        
        if not current_pass or not new_pass or not confirm_pass:
            style = {"marginTop": "10px", "textAlign": "center", "fontWeight": "bold", "color": "#ff6b6b"}
            return 'Please fill in all fields', style, no_update, '', ''
        
        if new_pass != confirm_pass:
            style = {"marginTop": "10px", "textAlign": "center", "fontWeight": "bold", "color": "#ff6b6b"}
            return 'New passwords do not match', style, no_update, '', ''
        
        # Change password in database
        success, message = finance_db.change_password(
            session_data['user_id'], 
            current_pass, 
            new_pass
        )
        
        if success:
            style = {"marginTop": "10px", "textAlign": "center", "fontWeight": "bold", "color": "#28a745"}
            return message, style, '', '', ''
        else:
            style = {"marginTop": "10px", "textAlign": "center", "fontWeight": "bold", "color": "#ff6b6b"}
            return message, style, no_update, '', ''
