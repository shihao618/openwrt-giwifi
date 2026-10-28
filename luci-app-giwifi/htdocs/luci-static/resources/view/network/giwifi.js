'use strict';

'require view';
'require dom';
'require fs';
'require ui';
'require uci';
'require form';
'require rpc';

/*
 * GiWiFi authentication - LuCI JavaScript view.
 *
 * The view follows the official LuCI JS API conventions:
 *   - a form.Map with separate top-level sections for status, settings,
 *     accounts and log, matching the Network -> Interfaces tab layout;
 *   - the status/log sections are backed by UI-only UCI placeholder
 *     sections, so they have unique DOM IDs and no duplicate tab names;
 *   - DummyValue display values are provided through cfgvalue(), which is
 *     the property actually consumed by DummyValue.renderWidget(); the
 *     textvalue() method is only used by GridSection table previews;
 *   - all dynamic strings are passed as array items to E()/dom.content()
 *     so that dom.append() creates text nodes instead of assigning HTML;
 *   - no theme overrides and no direct access to framework internals.
 */

const DEVICE_TYPES = [
	[ 'windows', 'Windows' ],
	[ 'ipad', 'iPad' ],
	[ 'iphone', 'iPhone' ],
	[ 'android', 'Android' ]
];

const VERSION = '2.1.7';

/* Query procd service state through ubus, the authoritative source. */
const callServiceList = rpc.declare({
	object: 'service',
	method: 'list',
	expect: { '': {} }
});

function serviceRunning(list) {
	const s = list && list['giwifi-auth'];

	if (!s || !s.instances)
		return false;

	return Object.keys(s.instances).some(function(k) {
		return s.instances[k] && s.instances[k].running;
	});
}

/* List network device names (excluding loopback). */
function listIfaces() {
	return fs.list('/sys/class/net').then(function(entries) {
		return (entries || []).map(function(e) {
			return e.name;
		}).filter(function(n) {
			return n != 'lo';
		});
	}).catch(function() {
		return [];
	});
}

/* Run a command; a non-zero exit code is not treated as a transport error. */
function exec(cmd, params) {
	return fs.exec(cmd, params).catch(function() {
		return { code: -1, stdout: '', stderr: '' };
	});
}

function sid(section) {
	return section['.name'] || section.name;
}

function accountSections() {
	return uci.sections('giwifi-auth', 'account') || [];
}

function deviceTypeLabel(type) {
	for (let i = 0; i < DEVICE_TYPES.length; i++)
		if (DEVICE_TYPES[i][0] == type)
			return DEVICE_TYPES[i][1];

	return type || 'windows';
}

/* UCI boolean values may be 1/0, true/false, yes/no or on/off. */
function isTruthy(value, fallback) {
	if (value == null || value === '')
		return !!fallback;

	return /^(1|true|yes|on)$/i.test(String(value));
}

/* GiWiFi icon used in the account ifacebox. */
function ifaceIcon() {
	return E('img', {
		'src': L.resource('icons/giwifi.svg'),
		'width': '16',
		'height': '16',
		'alt': '',
		'title': 'GiWiFi'
	});
}

return view.extend({
	load: function() {
		return Promise.all([
			uci.load('giwifi-auth'),
			/* network is only used to populate the interface list; a
			 * missing config or a denied read must not break the page. */
			L.resolveDefault(uci.load('network'), {}),
			Promise.resolve(VERSION),
			listIfaces(),
			exec('/usr/bin/giwifi-auth', [ 'log' ]),
			L.resolveDefault(callServiceList(), {}),
			/* firewall is used to restrict interface choices to the WAN
			 * zone; a missing config must not break the page. */
			L.resolveDefault(uci.load('firewall'), {})
		]);
	},

	/* Resolve a firewall zone's network names. */
	zoneNetworks: function(zone) {
		const nets = uci.get('firewall', sid(zone), 'network');

		if (Array.isArray(nets))
			return nets;

		return (nets || '').split(/\s+/).filter(Boolean);
	},

	/* Collect interface names belonging to WAN firewall zones.
	 *
	 * WAN zone names are not guaranteed to be "wan" (a common example is
	 * "wwan"), so zones are selected by masquerading, a wan-like zone
	 * name, or membership of the "wan"/"wan6" network. */
	collectWanDevs: function() {
		const devs = [];
		const self = this;

		function push(d) {
			if (Array.isArray(d)) {
				d.forEach(push);
				return;
			}

			(d || '').split(/\s+/).forEach(function(n) {
				if (n && /^[A-Za-z0-9_.:@-]+$/.test(n) &&
				    n.charAt(0) != '@' && n != 'br-lan' && n != 'lo' &&
				    devs.indexOf(n) == -1)
					devs.push(n);
			});
		}

		function addZone(zone) {
			self.zoneNetworks(zone).forEach(function(net) {
				if (!net || net.charAt(0) == '@')
					return;

				push(uci.get('network', net, 'device'));
				push(uci.get('network', net, 'ifname'));
			});

			push(uci.get('firewall', sid(zone), 'device'));
		}

		const zones = uci.sections('firewall', 'zone') || [];

		function zoneName(zone) {
			return (uci.get('firewall', sid(zone), 'name') || '').toLowerCase();
		}

		function zoneHasWanNet(zone) {
			const nets = self.zoneNetworks(zone);

			return nets.indexOf('wan') != -1 || nets.indexOf('wan6') != -1;
		}

		function zoneIsCandidate(zone) {
			return !/^lan([_-]|$)/.test(zoneName(zone));
		}

		/* Prefer zones containing the wan/wan6 network, then wan-like
		 * names, and only then the masquerading fallback. This avoids
		 * pulling in a masquerading guest zone when a real WAN exists. */
		let wanZones = zones.filter(function(zone) {
			return zoneIsCandidate(zone) && zoneHasWanNet(zone);
		});

		if (!wanZones.length)
			wanZones = zones.filter(function(zone) {
				return zoneIsCandidate(zone) &&
				       /(^|[_-])(wan|wwan|internet|uplink)([_-]|$)/.test(zoneName(zone));
			});

		if (!wanZones.length)
			wanZones = zones.filter(function(zone) {
				return zoneIsCandidate(zone) &&
				       isTruthy(uci.get('firewall', sid(zone), 'masq'), false);
			});

		if (wanZones.length) {
			wanZones.forEach(addZone);

			if (devs.length)
				return devs;
		}

		/* No usable firewall configuration: keep the old heuristic. */
		return this.collectNetworkWanDevs();
	},

	/* Fallback: all non-LAN interfaces from the network configuration. */
	collectNetworkWanDevs: function() {
		const devs = [];

		function push(d) {
			if (Array.isArray(d)) {
				d.forEach(push);
				return;
			}

			(d || '').split(/\s+/).forEach(function(n) {
				if (n && /^[A-Za-z0-9_.:@-]+$/.test(n) &&
				    n != 'br-lan' && n != 'lo' && devs.indexOf(n) == -1)
					devs.push(n);
			});
		}

		(uci.sections('network', 'interface') || []).forEach(function(s) {
			const name = sid(s);

			if (/^lan$/i.test(name))
				return;

			push(uci.get('network', name, 'device'));
			push(uci.get('network', name, 'ifname'));
		});

		return devs;
	},

	/* Render a placeholder first, then query the daemon asynchronously.
	 * The status command probes every configured interface and may block
	 * for several seconds on a broken link, so doing it in load() would
	 * delay the whole page. */
	statusValue: function() {
		const body = E('pre', {}, [ _('Detecting…') ]);
		const self = this;

		function refresh(ev) {
			if (ev)
				ev.preventDefault();

			dom.content(body, [ _('Detecting…') ]);

			return exec('/usr/bin/giwifi-auth', [ 'status' ]).then(function(res) {
				const text = (res.code === -1)
					? _('Failed to retrieve status. Check the network and try again.')
					: ((res.stdout || '').trim() || _('No enabled accounts'));

				dom.content(body, [ text ]);
			});
		}

		refresh();

		return E('div', {}, [
			body,
			E('button', {
				'class': 'btn cbi-button cbi-button-action',
				'click': ui.createHandlerFn(self, refresh)
			}, [ _('Refresh') ])
		]);
	},

	render: function(data) {
		const version = data[2],
		      netdevs = data[3],
		      logRes = data[4] || {},
		      svcList = data[5] || {};

		const running = serviceRunning(svcList),
		      mainEnabled = isTruthy(uci.get('giwifi-auth', 'main', 'enabled'), false),
		      logText = (logRes.stdout || '').trim() || _('No authentication log entries');

		const self = this;

		const m = new form.Map('giwifi-auth', _('GiWiFi Authentication'),
			_('Automatically log in to the GiWiFi campus portal. Supports multiple accounts and interfaces, and re-authenticates when the session drops.'));

		m.tabbed = true;

		/* Four top-level tabs, matching the Network -> Interfaces layout.
		 * The status/log UCI sections are UI-only placeholders; they carry
		 * no options and are ignored by the daemon. */
		const s1 = m.section(form.NamedSection, 'status', 'status', _('Status'));
		const s2 = m.section(form.NamedSection, 'main', 'giwifi', _('Settings'));
		const s3 = m.section(form.GridSection, 'account', _('Accounts'));
		const s4 = m.section(form.NamedSection, 'log', 'log', _('Log'));

		let o = s1.option(form.DummyValue, '_version', _('Version'));
		o.cfgvalue = function() {
			return version;
		};

		o = s1.option(form.DummyValue, '_daemon', _('Daemon'));
		o.cfgvalue = function() {
			return running ? _('Running') : _('Stopped');
		};

		o = s1.option(form.DummyValue, '_switch', _('Global Switch'));
		o.cfgvalue = function() {
			return mainEnabled ? _('Enabled') : _('Disabled');
		};

		o = s1.option(form.DummyValue, '_status', _('Account Status'));
		o.cfgvalue = function() {
			return self.statusValue();
		};

		o = s4.option(form.DummyValue, '_log', _('Recent Authentication Log'));
		o.cfgvalue = function() {
			return E('pre', {}, [ logText ]);
		};

		o = s2.option(form.Flag, 'enabled', _('Enable daemon'));
		o.default = '0';

		o = s2.option(form.Value, 'base_url', _('Portal base URL'));
		o.default = 'http://10.189.1.3';
		o.rmempty = false;
		o.validate = function(section_id, value) {
			if (!/^https?:\/\/\S+$/.test(value))
				return _('Invalid URL');

			return true;
		};

		o = s2.option(form.Value, 'interval', _('Poll interval (seconds)'));
		o.default = '30';
		o.datatype = 'range(10,3600)';
		o.rmempty = false;

		o = s2.option(form.Flag, 'ecmp_enabled', _('Automatic ECMP load balancing'));
		o.default = '1';
		o.description = _('Build a native ECMP default route from the interfaces bound by enabled accounts. Stop mwan3 before using this mode.');

		o = s2.option(form.Flag, 'iface_restart_enabled', _('Restart interface on schedule'));
		o.default = '0';

		o = s2.option(form.ListValue, 'iface_restart_time', _('Restart time'));
		o.default = '04:00';
		o.rmempty = false;
		o.description = _('Local time on the router');
		for (let hour = 0; hour < 24; hour++) {
			for (let minute = 0; minute < 60; minute += 15) {
				const value = ('0' + hour).slice(-2) + ':' + ('0' + minute).slice(-2);
				o.value(value, value);
			}
		}

		o = s2.option(form.ListValue, 'ua3f_sync_ua', _('UA3F terminal type synchronization'));
		o.value('', _('Do not synchronize (leave UA3F unchanged)'));
		DEVICE_TYPES.forEach(function(t) {
			o.value(t[0], t[1]);
		});
		o.default = '';

		/* Account list: a compact ifacebox on the left, details in the
		 * middle and the action buttons on the right, mirroring the
		 * Network -> Interfaces rows. */

		s3.anonymous = true;
		s3.addremove = true;
		s3.addbtntitle = _('Add Account');
		s3.modaltitle = function(section_id) {
			const user = uci.get('giwifi-auth', section_id, 'username');

			return user ? _('Edit Account') + ' - ' + user : _('Add Account');
		};

		o = s3.option(form.DummyValue, '_ifacebox');
		o.modalonly = false;
		o.textvalue = function(section_id) {
			const iface = uci.get('giwifi-auth', section_id, 'interface') || '-';
			const user = uci.get('giwifi-auth', section_id, 'username') || '-';
			const enabled = isTruthy(uci.get('giwifi-auth', section_id, 'enabled'), true);

			return E('div', { 'class': 'ifacebox' }, [
				E('div', { 'class': 'ifacebox-head' + (enabled ? ' active' : '') },
					E('strong', {}, [ iface ])),
				E('div', { 'class': 'ifacebox-body' }, [
					ifaceIcon(),
					E('br'),
					E('small', {}, [ user ])
				])
			]);
		};

		o = s3.option(form.DummyValue, '_ifacestat');
		o.modalonly = false;
		o.textvalue = function(section_id) {
			const enabled = uci.get('giwifi-auth', section_id, 'enabled');
			const rebind = uci.get('giwifi-auth', section_id, 'auto_rebind');

			return L.itemlist(E('div'), [
				_('Device type'), deviceTypeLabel(uci.get('giwifi-auth', section_id, 'device_type')),
				_('Account status'), isTruthy(enabled, true) ? _('Enabled') : _('Disabled'),
				_('Auto rebind'), isTruthy(rebind, false) ? _('Enabled') : _('Disabled')
			]);
		};

		let wanDevs = this.collectWanDevs();

		if (!wanDevs.length)
			wanDevs = netdevs.filter(function(n) {
				return /^[A-Za-z0-9_.:@-]+$/.test(n) &&
				       n != 'br-lan' && n != 'lo';
			});

		const ifaceChoices = wanDevs.slice();

		o = s3.option(form.ListValue, 'interface', _('Interface'));
		o.modalonly = true;
		o.rmempty = false;
		ifaceChoices.forEach(function(n) {
			o.value(n);
		});
		o.validate = function(section_id, value) {
			let dup = null;

			accountSections().forEach(function(s) {
				const other = sid(s);

				if (other == section_id)
					return;

				if (uci.get('giwifi-auth', other, 'interface') == value)
					dup = other;
			});

			if (dup != null)
				return _('Interface "%s" is already bound to account "%s". Please remove the duplicate binding first.').format(value, dup);

			return true;
		};

		o = s3.option(form.Value, 'username', _('Username'));
		o.modalonly = true;
		o.rmempty = false;

		o = s3.option(form.Value, 'password', _('Password'));
		o.modalonly = true;
		o.password = true;
		o.rmempty = false;

		o = s3.option(form.ListValue, 'device_type', _('Device type'));
		o.modalonly = true;
		DEVICE_TYPES.forEach(function(t) {
			o.value(t[0], t[1]);
		});
		o.default = 'windows';

		o = s3.option(form.Value, 'device_ua', _('Custom User-Agent (optional)'));
		o.modalonly = true;

		o = s3.option(form.Flag, 'auto_rebind', _('Automatically rebind MAC'));
		o.modalonly = true;

		/* Add row actions inside the standard action container so that
		 * the theme's flex layout applies to them as well. Pass the
		 * standard "Edit" label explicitly: this keeps the native edit
		 * button even if super() resolves directly to TableSection. */
		s3.renderRowActions = function(section_id) {
			const tdEl = this.super('renderRowActions', [ section_id, _('Edit') ]);
			const actions = tdEl.lastChild;

			if (!actions)
				return tdEl;

			const cur = uci.get('giwifi-auth', section_id, 'enabled'),
			      enabled = isTruthy(cur, true);

			const loginBtn = E('button', {
				'class': 'btn cbi-button cbi-button-apply',
				'click': ui.createHandlerFn(this, 'handleAccountLogin', section_id),
				'disabled': this.map.readonly || null
			}, [ _('Log in') ]);

			const toggleBtn = E('button', {
				'class': 'btn cbi-button cbi-button-neutral',
				'click': ui.createHandlerFn(this, 'handleAccountToggle', section_id),
				'disabled': this.map.readonly || null
			}, [ enabled ? _('Stop') : _('Enable') ]);

			/* Keep the native Edit/Delete buttons; add a fallback edit
			 * button if the super() implementation omitted it. */
			let editBtn = actions.querySelector('button.cbi-button-edit');

			if (!editBtn)
				editBtn = E('button', {
					'title': _('Edit'),
					'class': 'btn cbi-button cbi-button-edit',
					'click': ui.createHandlerFn(this, 'renderMoreOptionsModal', section_id)
				}, [ _('Edit') ]);

			const delBtn = actions.querySelector('button.cbi-button-remove');

			dom.content(actions, [ loginBtn, toggleBtn, editBtn, delBtn ].filter(Boolean));

			return tdEl;
		};

		/* Log in a single account. Anonymous section IDs are not known to
		 * the daemon before they are saved, so prefer the unique interface
		 * name, then the username, and only fall back to the section ID. */
		s3.handleAccountLogin = function(section_id, ev) {
			const target = uci.get('giwifi-auth', section_id, 'interface')
			            || uci.get('giwifi-auth', section_id, 'username')
			            || section_id;

			return exec('/usr/bin/giwifi-auth', [ 'login', target ]).then(function(res) {
				const out = ((res.stdout || '') + (res.stderr || '')).trim() || _('(no output)');

				ui.showModal(E('span', {}, [ _('Login result'), ' - ', target ]), [
					E('pre', {}, [ out ]),
					E('div', { 'class': 'button-row' }, [
						E('button', { 'class': 'btn cbi-button', 'click': ui.hideModal }, [ _('Close') ])
					])
				], 'cbi-modal');
			});
		};

		/* Toggle one account through the framework's direct UCI change
		 * flow. Only the enabled flag is touched here, so unrelated form
		 * input is not implicitly saved by a row action. */
		s3.handleAccountToggle = function(section_id, ev) {
			const cur = uci.get('giwifi-auth', section_id, 'enabled'),
			      enabled = isTruthy(cur, true);

			uci.set('giwifi-auth', section_id, 'enabled', enabled ? '0' : '1');

			return uci.save().then(function() {
				ui.changes.apply(true);
			}).catch(function(e) {
				ui.addNotification(null, E('p', {}, [
					e && e.message ? e.message : e
				]), 'error');
			});
		};

		return m.render();
	},

	/* Reject duplicate interface bindings after the form has been parsed. */
	findDuplicateIface: function() {
		const seen = Object.create(null);
		let dup = null;

		accountSections().forEach(function(s) {
			const name = sid(s),
			      iface = uci.get('giwifi-auth', name, 'interface');

			if (!iface)
				return;

			if (seen[iface] != null)
				dup = iface;

			seen[iface] = name;
		});

		return dup;
	},

	/* Save and apply through the framework's standard change flow.
	 * The duplicate-interface check runs in Map.save()'s callback, i.e.
	 * after the form has been parsed but before UCI changes are submitted
	 * to rpcd, so an invalid binding never enters the pending changeset. */
	handleSaveApply: function(ev, mode) {
		const self = this;
		const mapNode = document.querySelector('#maincontent .cbi-map');
		const mapObj = mapNode ? dom.findClassInstance(mapNode) : null;

		function validateBindings() {
			const dup = self.findDuplicateIface();

			if (dup != null)
				throw new Error(_('Interface "%s" is bound to multiple accounts. Please remove the duplicate binding first.').format(dup));
		}

		const save = mapObj
			? mapObj.save(validateBindings, true)
			: this.handleSave(ev);

		return save.then(function() {
			return ui.changes.apply(mode == '0');
		}).catch(function(e) {
			ui.addNotification(null, E('p', {}, [
				_('Failed to save: %s').format(e && e.message ? e.message : e)
			]), 'error');
		});
	}
});
