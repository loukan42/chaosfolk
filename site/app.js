(function () {
  "use strict";

  var config = window.CHAOSFOLK_CONFIG || {};
  var api = String(config.apiBase || "").replace(/\/+$/, "");
  var $ = function (id) { return document.getElementById(id); };

  var form = $("audit-form");
  var submit = $("submit");
  var formError = $("form-error");
  var statusBox = $("status");
  var turnstileToken = "";
  var turnstileWidget = null;
  var pollTimer = null;
  var clockTimer = null;

  function showError(message) {
    formError.textContent = message;
    formError.hidden = !message;
  }

  function request(path, options) {
    return fetch(api + path, options).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (body) {
        if (!response.ok) {
          var error = new Error(typeof body.detail === "string" ? body.detail : "The server refused the request.");
          error.status = response.status;
          throw error;
        }
        return body;
      });
    });
  }

  function renderQuota(quota) {
    var box = $("quota");
    $("quota-count").textContent = String(quota.remaining);
    $("quota-label").textContent = quota.remaining === 1 ? "free audit left today" : "free audits left today";
    box.classList.toggle("empty", quota.remaining === 0);
    if (quota.remaining === 0) {
      var reset = new Date(quota.resets_at);
      $("quota-label").textContent = "free audits left today. New ones at " +
        reset.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) + ".";
      submit.disabled = true;
    }
  }

  function loadQuota() {
    return request("/api/quota").then(renderQuota).catch(function () {
      $("quota-count").textContent = "-";
      $("quota-label").textContent = "The audit server cannot be reached right now.";
    });
  }

  function closedForm() {
    submit.disabled = true;
    $("quota-count").textContent = "0";
    $("quota-label").textContent = "Hosted audits are not open yet. Install Chaosfolk below to run one now.";
  }

  function mountTurnstile() {
    if (!config.turnstileSiteKey) return;
    window.onTurnstileLoad = function () {
      turnstileWidget = window.turnstile.render("#turnstile", {
        sitekey: config.turnstileSiteKey,
        theme: "dark",
        callback: function (token) { turnstileToken = token; },
        "expired-callback": function () { turnstileToken = ""; },
        "error-callback": function () { turnstileToken = ""; }
      });
    };
    var script = document.createElement("script");
    script.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?onload=onTurnstileLoad&render=explicit";
    script.async = true;
    document.head.appendChild(script);
  }

  function resetTurnstile() {
    turnstileToken = "";
    if (turnstileWidget !== null && window.turnstile) window.turnstile.reset(turnstileWidget);
  }

  function minutesSince(iso) {
    return Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 60000));
  }

  function renderAudit(audit) {
    form.hidden = true;
    statusBox.hidden = false;
    $("status-url").textContent = audit.url;
    var progress = $("progress");
    var detail = $("status-detail");
    var link = $("report-link");
    progress.className = "progress";
    progress.firstElementChild.style.width = "";
    $("report-actions").hidden = true;
    $("new-audit").hidden = true;
    $("status-note").hidden = false;
    clearInterval(clockTimer);

    if (audit.status === "queued") {
      $("status-title").textContent = "Waiting in line";
      var ahead = Math.max(audit.position - 1, 0);
      detail.textContent = ahead === 0 ? "Your audit starts next." :
        ahead + (ahead === 1 ? " audit is" : " audits are") + " ahead of you. Audits run one at a time.";
      progress.classList.add("waiting");
    } else if (audit.status === "running") {
      $("status-title").textContent = audit.phase || "Audit running";
      var limit = audit.time_limit_minutes;
      var tick = function () {
        var elapsed = minutesSince(audit.started_at);
        detail.textContent = "Running for " + elapsed + " min. The users stop after " + limit +
          " min, then the report is written.";
        progress.firstElementChild.style.width = Math.min(95, Math.round((elapsed / (limit + 3)) * 100)) + "%";
      };
      tick();
      clockTimer = setInterval(tick, 15000);
    } else if (audit.status === "done") {
      $("status-title").textContent = "Your report is ready";
      detail.textContent = "Keep the link: the report is deleted after 7 days.";
      progress.firstElementChild.style.width = "100%";
      link.href = audit.report_url;
      $("download-link").href = audit.download_url;
      $("copy-link").textContent = "Copy the link";
      $("share-link").hidden = typeof navigator.share !== "function";
      $("report-actions").hidden = false;
      $("status-note").hidden = true;
      $("new-audit").hidden = false;
    } else {
      $("status-title").textContent = audit.status === "expired" ? "This report was deleted" : "The audit stopped";
      detail.textContent = audit.error || (audit.status === "expired" ? "Reports stay online for 7 days." : "No report was produced.");
      progress.classList.add("failed");
      $("status-note").hidden = true;
      $("new-audit").hidden = false;
    }
  }

  function follow(id) {
    clearTimeout(pollTimer);
    request("/api/audits/" + encodeURIComponent(id)).then(function (audit) {
      renderAudit(audit);
      if (audit.status === "queued" || audit.status === "running") {
        pollTimer = setTimeout(function () { follow(id); }, audit.status === "queued" ? 4000 : 6000);
      }
    }).catch(function (error) {
      if (error.status === 404) {
        history.replaceState(null, "", location.pathname);
        backToForm();
        showError(error.message);
        return;
      }
      pollTimer = setTimeout(function () { follow(id); }, 10000);
    });
  }

  function backToForm() {
    clearTimeout(pollTimer);
    clearInterval(clockTimer);
    statusBox.hidden = true;
    form.hidden = false;
    showError("");
    resetTurnstile();
    loadQuota();
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    showError("");
    var url = $("url").value.trim();
    if (!url) { showError("Enter the address of your site."); $("url").focus(); return; }
    if (!$("authorized").checked) { showError("Confirm that you own this site or are authorized to test it."); return; }
    if (config.turnstileSiteKey && !turnstileToken) { showError("Wait for the anti-robot check to finish, then try again."); return; }
    var lang = form.querySelector("input[name=lang]:checked").value;
    submit.disabled = true;
    submit.textContent = "Checking the address";
    request("/api/audits", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: url, lang: lang, authorized: true, turnstile: turnstileToken })
    }).then(function (audit) {
      history.replaceState(null, "", "#audit=" + encodeURIComponent(audit.id));
      if (audit.quota) renderQuota(audit.quota);
      renderAudit(audit);
      follow(audit.id);
    }).catch(function (error) {
      showError(error.message || "The audit server cannot be reached right now.");
      resetTurnstile();
      loadQuota();
    }).then(function () {
      submit.textContent = "Start the audit";
      if ($("quota-count").textContent !== "0") submit.disabled = false;
    });
  });

  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text);
    return new Promise(function (resolve, reject) {
      var field = document.createElement("textarea");
      field.value = text;
      field.setAttribute("readonly", "");
      field.style.position = "fixed";
      field.style.opacity = "0";
      document.body.appendChild(field);
      field.select();
      var ok = false;
      try { ok = document.execCommand("copy"); } catch (error) { ok = false; }
      document.body.removeChild(field);
      if (ok) { resolve(); } else { reject(new Error("copy")); }
    });
  }

  $("copy-link").addEventListener("click", function () {
    var button = this;
    var url = $("report-link").href;
    copyText(url).then(function () {
      button.textContent = "Link copied";
    }).catch(function () {
      window.prompt("Copy this link:", url);
    });
  });

  $("share-link").addEventListener("click", function () {
    navigator.share({ title: "Chaosfolk report", text: "Chaosfolk audit of " + $("status-url").textContent,
                      url: $("report-link").href }).catch(function () {});
  });

  $("new-audit").addEventListener("click", function () {
    history.replaceState(null, "", location.pathname);
    $("url").value = "";
    backToForm();
  });

  if (!api) {
    closedForm();
    return;
  }
  mountTurnstile();
  var match = /audit=([A-Za-z0-9_-]+)/.exec(location.hash);
  loadQuota();
  if (match) follow(match[1]);
})();
