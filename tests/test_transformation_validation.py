"""Transformation-validation test suite.

These tests validate the *transformation process itself* — the helper functions
that underpin the Angular → React pipeline — rather than the generated
application.  They verify that:

  1. parse_angular_source correctly identifies Angular artefacts
  2. validate_react_code correctly detects React issues and Angular remnants
  3. Key Angular → React mapping patterns are structurally sound
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.transformation

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

from tools.functions.angular_parser import parse_angular_source
from tools.functions.react_validator import validate_react_code


def _angular_component(name: str = "UserList") -> str:
    return f"""
import {{ Component, Input, Output, EventEmitter, OnInit, OnDestroy }} from '@angular/core';
import {{ UserService }} from '../services/user.service';

@Component({{
  selector: 'app-{name.lower()}',
  templateUrl: './{name.lower()}.component.html',
  styleUrls: ['./{name.lower()}.component.scss'],
}})
export class {name}Component implements OnInit, OnDestroy {{
  @Input() pageSize: number = 10;
  @Output() userSelected = new EventEmitter<User>();

  users: User[] = [];
  isLoading = false;

  constructor(private userService: UserService) {{}}

  ngOnInit(): void {{
    this.isLoading = true;
    this.userService.getUsers().subscribe(users => {{
      this.users = users;
      this.isLoading = false;
    }});
  }}

  ngOnDestroy(): void {{
    // cleanup
  }}

  selectUser(user: User): void {{
    this.userSelected.emit(user);
  }}
}}
"""


def _angular_service() -> str:
    return """
import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { BehaviorSubject, Observable } from 'rxjs';

@Injectable({ providedIn: 'root' })
export class UserService {
  private usersSubject = new BehaviorSubject<User[]>([]);
  users$ = this.usersSubject.asObservable();
  private currentUser: User | null = null;

  constructor(private http: HttpClient) {}

  getUsers(): Observable<User[]> {
    return this.http.get<User[]>('/api/users');
  }

  setCurrentUser(user: User): void {
    this.currentUser = user;
  }
}
"""


def _angular_module() -> str:
    return """
import { NgModule } from '@angular/core';
import { RouterModule, Routes } from '@angular/router';
import { ReactiveFormsModule } from '@angular/forms';
import { UserListComponent } from './users/user-list.component';

const routes: Routes = [
  { path: 'users', component: UserListComponent },
];

@NgModule({
  declarations: [UserListComponent],
  imports: [RouterModule.forChild(routes), ReactiveFormsModule],
})
export class UsersModule {}
"""


def _react_clean() -> str:
    return """
import React, { useState, useEffect, useCallback, memo } from 'react';
import { DhlButton, DhlInputField } from '@dhl-official/react-library';

interface UserListProps {
  pageSize?: number;
  onUserSelected: (user: User) => void;
}

const UserList = memo(({ pageSize = 10, onUserSelected }: UserListProps) => {
  const [users, setUsers] = useState<User[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    setIsLoading(true);
    fetch('/api/users', { signal: controller.signal })
      .then(r => r.json())
      .then(data => { setUsers(data); setIsLoading(false); })
      .catch(() => setIsLoading(false));
    return () => controller.abort();
  }, []);

  const handleSelect = useCallback((user: User) => {
    onUserSelected(user);
  }, [onUserSelected]);

  if (isLoading) return <div role="status">Loading…</div>;

  return (
    <ul>
      {users.map(u => (
        <li key={u.id}>
          <DhlButton onDhlClick={() => handleSelect(u)}>{u.name}</DhlButton>
        </li>
      ))}
    </ul>
  );
});

export default UserList;
"""


def _react_with_class_component() -> str:
    return """
import React from 'react';

class UserList extends React.Component {
  render() {
    return <div>users</div>;
  }
}

export default UserList;
"""


def _react_with_angular_remnants() -> str:
    return """
import React from 'react';

const UserList = () => (
  <div *ngIf="users.length">
    {users.map(u => <li *ngFor="let u of users">{u.name}</li>)}
  </div>
);
"""


def _react_with_implicit_any() -> str:
    return """
import React, { useState } from 'react';

const UserForm = () => {
  const [data, setData] = useState<any>(null);
  const handleChange = (e: any) => setData(e.target.value);
  return <input onChange={handleChange} />;
};
"""


# ===========================================================================
# parse_angular_source — artefact detection
# ===========================================================================

class TestAngularParserArtefactDetection:

    def test_detects_component_decorator(self):
        result = parse_angular_source(_angular_component())
        assert "@Component" in result

    def test_detects_injectable_service(self):
        result = parse_angular_source(_angular_service())
        assert "@Injectable" in result

    def test_detects_ngmodule(self):
        result = parse_angular_source(_angular_module())
        assert "@NgModule" in result

    def test_detects_input_decorator(self):
        result = parse_angular_source(_angular_component())
        assert "@Input" in result

    def test_detects_output_decorator(self):
        result = parse_angular_source(_angular_component())
        assert "@Output" in result

    def test_detects_multiple_artefacts_in_one_source(self):
        combined = _angular_component() + "\n" + _angular_service()
        result = parse_angular_source(combined)
        assert "@Component" in result
        assert "@Injectable" in result

    def test_includes_file_name_in_output(self):
        result = parse_angular_source(_angular_component(), file_name="user-list.component.ts")
        assert "user-list.component.ts" in result

    def test_reports_source_length(self):
        src = _angular_component()
        result = parse_angular_source(src)
        assert "characters" in result

    def test_warns_on_non_angular_code(self):
        result = parse_angular_source("const x = 42;", file_name="util.ts")
        assert "WARNING" in result

    def test_error_on_empty_input(self):
        result = parse_angular_source("")
        assert "error" in result.lower()

    def test_error_on_whitespace_only_input(self):
        result = parse_angular_source("   \n\t  ")
        assert "error" in result.lower()

    def test_error_on_oversized_input(self):
        huge = "x" * 200_001
        result = parse_angular_source(huge)
        assert "error" in result.lower()
        assert "too large" in result.lower()


# ===========================================================================
# parse_angular_source — lifecycle hook identification
# ===========================================================================

class TestAngularParserLifecycleHooks:

    def test_detects_ngoninit(self):
        result = parse_angular_source(_angular_component())
        assert "OnInit" in result or "ngOnInit" in result

    def test_detects_ngondestroy(self):
        result = parse_angular_source(_angular_component())
        assert "OnDestroy" in result or "ngOnDestroy" in result

    def test_detects_behaviorsubject_in_service(self):
        result = parse_angular_source(_angular_service())
        assert "BehaviorSubject" in result

    def test_detects_observable_pattern(self):
        result = parse_angular_source(_angular_service())
        assert "Observable" in result

    def test_detects_http_client_usage(self):
        result = parse_angular_source(_angular_service())
        assert "HttpClient" in result

    def test_detects_reactive_forms_in_module(self):
        result = parse_angular_source(_angular_module())
        assert "ReactiveFormsModule" in result

    def test_detects_router_in_module(self):
        result = parse_angular_source(_angular_module())
        assert "RouterModule" in result or "Routes" in result


# ===========================================================================
# validate_react_code — correctness checks
# ===========================================================================

class TestReactValidatorCleanCode:

    def test_clean_component_passes(self):
        result = validate_react_code(_react_clean())
        assert "No issues found" in result or result.count("[ERROR]") == 0

    def test_empty_input_returns_error(self):
        result = validate_react_code("")
        assert "error" in result.lower()

    def test_whitespace_input_returns_error(self):
        result = validate_react_code("   ")
        assert "error" in result.lower()


class TestReactValidatorAngularRemnants:

    def test_detects_ngif_directive(self):
        code = "const X = () => <div *ngIf='show'>hi</div>;"
        result = validate_react_code(code)
        assert "ERROR" in result
        assert "no-angular-remnants" in result

    def test_detects_ngfor_directive(self):
        code = "const X = () => <li *ngFor='let i of items'>{i}</li>;"
        result = validate_react_code(code)
        assert "ERROR" in result
        assert "no-angular-remnants" in result

    def test_detects_component_decorator(self):
        code = "@Component({ selector: 'app-x' })\nexport class X {}"
        result = validate_react_code(code)
        assert "ERROR" in result

    def test_detects_injectable_decorator(self):
        code = "@Injectable({ providedIn: 'root' })\nexport class MyService {}"
        result = validate_react_code(code)
        assert "ERROR" in result

    def test_detects_ngmodel(self):
        code = "const X = () => <input [(ngModel)]='value' />;"
        result = validate_react_code(code)
        assert "ERROR" in result


class TestReactValidatorAntiPatterns:

    def test_detects_class_component(self):
        result = validate_react_code(_react_with_class_component())
        assert "ERROR" in result
        assert "no-class-components" in result

    def test_detects_implicit_any(self):
        result = validate_react_code(_react_with_implicit_any())
        assert "ERROR" in result
        assert "no-implicit-any" in result

    def test_detects_console_log(self):
        code = "import React from 'react';\nconst X = () => { console.log('debug'); return null; };"
        result = validate_react_code(code)
        assert "WARNING" in result
        assert "no-console" in result

    def test_detects_missing_key_in_map(self):
        code = "import React from 'react';\nconst X = ({items}) => <ul>{items.map(i => <li>{i}</li>)}</ul>;"
        result = validate_react_code(code)
        assert "WARNING" in result
        assert "jsx-key" in result

    def test_detects_missing_react_import_with_hooks(self):
        code = "const X = () => { const [x, setX] = useState(0); return null; };"
        result = validate_react_code(code)
        assert "WARNING" in result
        assert "react-import" in result


# ===========================================================================
# Angular → React transformation pattern contracts
# ===========================================================================

class TestTransformationPatternContracts:
    """Verify that the fundamental Angular→React mapping patterns are correct.

    These tests document the expected transformation contracts and will catch
    regressions if the parser or validator helper functions deviate from them.
    """

    def test_input_decorator_signals_prop(self):
        src = "@Input() users: User[] = [];"
        result = parse_angular_source(src, "user-list.component.ts")
        assert "@Input" in result, "Parser must surface @Input for props mapping"

    def test_output_emitter_signals_callback_prop(self):
        src = "@Output() userSelected = new EventEmitter<User>();"
        result = parse_angular_source(src, "user-list.component.ts")
        assert "@Output" in result, "Parser must surface @Output for callback-prop mapping"

    def test_behaviorsubject_signals_context_need(self):
        src = "private usersSubject = new BehaviorSubject<User[]>([]);"
        result = parse_angular_source(src, "user.service.ts")
        assert "BehaviorSubject" in result, "Parser must surface BehaviorSubject for Context mapping"

    def test_react_validator_accepts_useeffect_with_deps(self):
        code = (
            "import React, { useEffect } from 'react';\n"
            "const X = () => { useEffect(() => { fetch('/x'); }, []); return null; };"
        )
        result = validate_react_code(code)
        assert "[ERROR]" not in result

    def test_react_validator_accepts_memo_component(self):
        code = (
            "import React, { memo } from 'react';\n"
            "const UserCard = memo(({ user }) => <div>{user.name}</div>);\n"
            "export default UserCard;"
        )
        result = validate_react_code(code)
        assert "[ERROR]" not in result

    def test_dhl_button_usage_is_valid_react(self):
        code = (
            "import React from 'react';\n"
            "import { DhlButton } from '@dhl-official/react-library';\n"
            "const X = ({ onClick }) => <DhlButton onDhlClick={onClick}>Go</DhlButton>;\n"
        )
        result = validate_react_code(code)
        assert "[ERROR]" not in result

    def test_raw_html_button_triggers_no_parser_error_but_needs_duil(self):
        """The static validator doesn't catch raw <button>; DHL compliance is the agent's job."""
        code = (
            "import React from 'react';\n"
            "const X = () => <button onClick={() => {}}>Click</button>;\n"
        )
        result = validate_react_code(code)
        # No Angular remnants, no class components — static validator passes
        assert "no-angular-remnants" not in result

    def test_functional_component_no_class_errors(self):
        code = (
            "import React, { useState } from 'react';\n"
            "const Counter = () => {\n"
            "  const [count, setCount] = useState(0);\n"
            "  return <button onClick={() => setCount(c => c + 1)}>{count}</button>;\n"
            "};\n"
        )
        result = validate_react_code(code)
        assert "no-class-components" not in result
