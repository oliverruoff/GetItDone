"""Small JSON-compatible domain model. All hierarchy rules live here."""

from datetime import datetime, timezone
from uuid import uuid4


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return str(uuid4())


def empty_data():
    return {
        "schema_version": 1,
        "settings": {"default_workdir": "", "default_agent": "opencode"},
        "categories": [],
        "items": [],
        "sessions": [],
    }


class Notebook:
    def __init__(self, data=None):
        self.data = data if data is not None else empty_data()

    @property
    def items(self):
        return self.data["items"]

    def get(self, ident):
        return next((i for i in self.items if i["id"] == ident), None)

    def children(self, parent=None):
        return sorted((i for i in self.items if i["parent_id"] == parent), key=lambda i: i["position"])

    def descendants(self, ident):
        result = []
        for child in self.children(ident):
            result.append(child)
            result.extend(self.descendants(child["id"]))
        return result

    def ancestors(self, ident):
        result = []
        item = self.get(ident)
        while item and item["parent_id"]:
            item = self.get(item["parent_id"])
            if item:
                result.append(item)
        return result

    def add(self, text="New item", parent=None, after=None):
        if parent and not self.get(parent):
            raise ValueError("Parent item does not exist.")
        siblings = self.children(parent)
        pos = len(siblings)
        if after:
            pos = next((n + 1 for n, i in enumerate(siblings) if i["id"] == after), pos)
            for sibling in siblings[pos:]:
                sibling["position"] += 1
        item = dict(
            id=uid(),
            parent_id=parent,
            position=pos,
            text=text,
            notes="",
            done=False,
            category_id=self.get(parent)["category_id"] if parent else None,
            reminder=None,
            created_at=now_iso(),
            updated_at=now_iso(),
        )
        self.items.append(item)
        for ancestor in self.ancestors(item["id"]):
            ancestor["done"] = False
        return item

    def update(self, ident, **values):
        item = self.get(ident)
        if item:
            item.update(values, updated_at=now_iso())

    def complete(self, ident, done):
        affected = (
            [self.get(ident), *self.descendants(ident)] if done else [self.get(ident), *self.ancestors(ident)]
        )
        before = {item["id"]: item["done"] for item in affected if item is not None}
        for item in affected:
            if item is not None:
                self.update(item["id"], done=done)
        if not done:
            for ancestor in self.ancestors(ident):
                self.update(ancestor["id"], done=False)
        return before

    def restore_completion(self, snapshot):
        for ident, done in snapshot.items():
            self.update(ident, done=done)
        for ident, done in snapshot.items():
            if not done:
                for ancestor in self.ancestors(ident):
                    self.update(ancestor["id"], done=False)

    def normalize(self, parent):
        for pos, item in enumerate(self.children(parent)):
            item["position"] = pos

    def move(self, ident, delta):
        item = self.get(ident)
        siblings = self.children(item["parent_id"])
        index = siblings.index(item)
        other = index + delta
        if 0 <= other < len(siblings):
            siblings[index], siblings[other] = siblings[other], siblings[index]
            for pos, sibling in enumerate(siblings):
                sibling["position"] = pos

    def relocate(self, ident, parent=None, before=None):
        """Move an entire subtree, rejecting cycles and invalid insertion targets."""
        item = self.get(ident)
        if item is None or parent == ident or (parent is not None and self.get(parent) is None):
            return False
        if parent in {child["id"] for child in self.descendants(ident)}:
            return False
        siblings = [child for child in self.children(parent) if child["id"] != ident]
        if before == ident:
            return False
        index = len(siblings)
        if before is not None:
            target = next((child for child in siblings if child["id"] == before), None)
            if target is None:
                return False
            index = siblings.index(target)
        old_parent = item["parent_id"]
        self.update(ident, parent_id=parent)
        siblings.insert(index, item)
        for position, sibling in enumerate(siblings):
            self.update(sibling["id"], position=position)
        self.normalize(old_parent)
        if not item["done"]:
            for ancestor in self.ancestors(ident):
                self.update(ancestor["id"], done=False)
        return True

    def indent(self, ident, out=False):
        item = self.get(ident)
        old_parent = item["parent_id"]
        if out:
            parent = self.get(old_parent)
            if not parent:
                return
            target = parent["parent_id"]
            pos = parent["position"] + 1
        else:
            siblings = self.children(old_parent)
            index = siblings.index(item)
            if index == 0:
                return
            parent = siblings[index - 1]
            target, pos = parent["id"], len(self.children(parent["id"]))
        for sibling in self.children(target):
            if sibling["position"] >= pos:
                sibling["position"] += 1
        self.update(ident, parent_id=target, position=pos)
        self.normalize(old_parent)
        if not item["done"]:
            for ancestor in self.ancestors(ident):
                self.update(ancestor["id"], done=False)

    def delete(self, ident):
        item = self.get(ident)
        ids = {ident, *(i["id"] for i in self.descendants(ident))}
        self.data["items"] = [i for i in self.items if i["id"] not in ids]
        # Live processes belong to the terminal manager, not these persistent links.
        self.data["sessions"] = [s for s in self.data["sessions"] if s["item_id"] not in ids]
        self.normalize(item["parent_id"])

    def delete_category(self, ident):
        self.data["categories"] = [c for c in self.data["categories"] if c["id"] != ident]
        for item in self.items:
            if item["category_id"] == ident:
                self.update(item["id"], category_id=None)

    def visible(self, query="", status="open", category=None):
        query = query.casefold()
        direct = {
            i["id"]
            for i in self.items
            if (not query or query in (i["text"] + "\n" + i["notes"]).casefold())
            and (status == "all" or i["done"] == (status == "done"))
            and (not category or i["category_id"] == category)
        }
        visible = set(direct)
        for ident in direct:
            visible.update(i["id"] for i in self.ancestors(ident))
        return visible, direct
