/* Attachment picker: preview selected files, remove individually, add more.
 * Works with <input type="file" multiple> by keeping a DataTransfer store
 * in sync with input.files. Supports browse, add-more, drag & drop.
 * Usage: wrap input in [data-attachment-picker], include this script once.
 */
(function () {
  function formatSize(bytes) {
    if (!bytes && bytes !== 0) return "";
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  }

  function fileKey(f) {
    return f.name + "|" + f.size + "|" + f.lastModified;
  }

  function initPicker(root) {
    if (root._pickerInit) return;
    root._pickerInit = true;
    var input = root.querySelector('input[type="file"]');
    var list = root.querySelector("[data-picker-list]");
    var emptyMsg = root.querySelector("[data-picker-empty]");
    var countEl = root.querySelector("[data-picker-count]");
    var dropzone = root.querySelector("[data-picker-dropzone]");
    if (!input || !list) return;

    // Ensure multiple so add-more can accumulate
    input.setAttribute("multiple", "multiple");

    var store = new DataTransfer();
    var seen = new Set();

    function syncInput() {
      input.files = store.files;
    }

    function render() {
      var files = Array.from(store.files);
      list.innerHTML = "";
      if (!files.length) {
        if (emptyMsg) emptyMsg.style.display = "";
        if (countEl) countEl.textContent = "";
        return;
      }
      if (emptyMsg) emptyMsg.style.display = "none";
      if (countEl) {
        var total = files.reduce(function (s, f) { return s + (f.size || 0); }, 0);
        countEl.textContent = files.length + " file" + (files.length > 1 ? "s" : "") + " selected (" + formatSize(total) + ")";
      }
      files.forEach(function (f, idx) {
        var li = document.createElement("li");
        li.className = "flex items-center justify-between gap-3 px-4 py-3 bg-white border border-slate-200 rounded-xl shadow-sm";
        var left = document.createElement("div");
        left.className = "flex items-center gap-3 min-w-0";
        left.innerHTML =
          '<span class="w-9 h-9 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center shrink-0">' +
          '<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">' +
          '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13"/>' +
          "</svg></span>";
        var meta = document.createElement("div");
        meta.className = "min-w-0";
        var name = document.createElement("p");
        name.className = "text-xs font-bold text-slate-800 truncate";
        name.textContent = f.name;
        name.title = f.name;
        var size = document.createElement("p");
        size.className = "text-[10px] text-slate-400 font-medium";
        size.textContent = formatSize(f.size);
        meta.appendChild(name);
        meta.appendChild(size);
        left.appendChild(meta);

        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "shrink-0 px-3 py-1.5 text-[10px] font-black uppercase tracking-widest text-red-600 bg-red-50 border border-red-100 rounded-lg hover:bg-red-600 hover:text-white transition-all";
        btn.textContent = "Remove";
        btn.setAttribute("aria-label", "Remove " + f.name);
        btn.addEventListener("click", function () {
          removeAt(idx);
        });

        li.appendChild(left);
        li.appendChild(btn);
        list.appendChild(li);
      });
    }

    function addFiles(fileList) {
      var added = 0;
      Array.from(fileList).forEach(function (f) {
        var k = fileKey(f);
        if (seen.has(k)) return;
        seen.add(k);
        store.items.add(f);
        added++;
      });
      if (added) {
        syncInput();
        render();
      } else {
        // reset input so same-file re-select still fires change
        input.value = "";
      }
    }

    function removeAt(idx) {
      var files = Array.from(store.files);
      var next = new DataTransfer();
      seen = new Set();
      files.forEach(function (f, i) {
        if (i === idx) return;
        next.items.add(f);
        seen.add(fileKey(f));
      });
      store = next;
      syncInput();
      render();
    }

    function clearAll() {
      store = new DataTransfer();
      seen = new Set();
      syncInput();
      input.value = "";
      render();
    }

    input.addEventListener("change", function () {
      if (input.files && input.files.length) addFiles(input.files);
      // keep input in sync (addFiles already synced); clear raw value quirk
      syncInput();
      // allow selecting the same file again later
      // (input.files is now the store; value reset won't clear files in all browsers,
      // so re-assign after tick)
      setTimeout(function () { try { if (!store.files.length) input.value = ""; } catch (e) {} }, 0);
    });

    root.querySelectorAll("[data-picker-browse]").forEach(function (btn) {
      btn.addEventListener("click", function () { input.click(); });
    });

    var clearBtn = root.querySelector("[data-picker-clear]");
    if (clearBtn) clearBtn.addEventListener("click", clearAll);

    // Drag & drop
    if (dropzone) {
      ["dragenter", "dragover"].forEach(function (ev) {
        dropzone.addEventListener(ev, function (e) {
          e.preventDefault();
          dropzone.classList.add("border-nigeria-green", "bg-nigeria-light/40");
        });
      });
      ["dragleave", "drop"].forEach(function (ev) {
        dropzone.addEventListener(ev, function (e) {
          e.preventDefault();
          dropzone.classList.remove("border-nigeria-green", "bg-nigeria-light/40");
        });
      });
      dropzone.addEventListener("drop", function (e) {
        if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length) addFiles(e.dataTransfer.files);
      });
    }

    // Expose for form reset handling
    root._attachmentPickerClear = clearAll;
    var form = input.closest("form");
    if (form && !form._pickerResetBound) {
      form._pickerResetBound = true;
      form.addEventListener("reset", function () {
        setTimeout(function () {
          root.querySelectorAll("[data-attachment-picker]").forEach(function (r) {
            if (r._attachmentPickerClear) r._attachmentPickerClear();
          });
          // also clear self if this root is the picker
          if (root._attachmentPickerClear && !root.querySelector("[data-attachment-picker]")) root._attachmentPickerClear();
        }, 0);
      });
    }

    render();
  }

  function initAll() {
    document.querySelectorAll("[data-attachment-picker]").forEach(initPicker);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAll);
  } else {
    initAll();
  }
})();
