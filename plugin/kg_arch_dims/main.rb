require 'sketchup.rb'
require 'json'
require_relative 'law'

module KG
  module ArchDims
    PLUGIN_DIR = File.dirname(__FILE__)
    DATA_FILE = File.join(PLUGIN_DIR, 'data.json')
    USER_FILE = File.join(PLUGIN_DIR, 'user_data.json')
    Law.cache_file = File.join(PLUGIN_DIR, 'law_cache.json')
    SNAP_FILE = File.join(PLUGIN_DIR, 'law_snapshot.json')
    BUNDLED_SNAP = File.join(PLUGIN_DIR, 'law_snapshot_bundled.json')
    REPO_RAW = 'https://raw.githubusercontent.com/geonumul/ArchiDims/main/'
    WEEK = 7 * 86_400
    DEFAULT_SNAP_URL = 'https://raw.githubusercontent.com/geonumul/ArchiDims/main/law_snapshot.json'

    def self.read_json(path)
      return [] unless File.exist?(path)
      JSON.parse(File.read(path, encoding: 'UTF-8'))
    rescue StandardError => e
      puts "건축 치수 사전: #{File.basename(path)} 읽기 실패 - #{e.message}"
      []
    end

    def self.payload
      base = read_json(DATA_FILE)
      user = read_json(USER_FILE).each { |h| h['user'] = true }
      JSON.generate(base + user)
    end

    def self.save_user(json)
      list = JSON.parse(json)
      File.open(USER_FILE, 'w:UTF-8') { |f| f.write(JSON.pretty_generate(list)) }
      true
    rescue StandardError => e
      UI.messagebox("저장 실패: #{e.message}")
      false
    end

    def self.pref(k, d = nil)
      Sketchup.read_default('KG_ArchDims', k, d)
    end

    def self.set_pref(k, v)
      Sketchup.write_default('KG_ArchDims', k, v)
    end

    def self.snapshot
      [SNAP_FILE, BUNDLED_SNAP].each do |f|
        next unless File.exist?(f)
        d = JSON.parse(File.read(f, encoding: 'UTF-8')) rescue nil
        return d if d.is_a?(Hash) && d['items']
      end
      nil
    end

    def self.config_hash
      {
        'oc' => Law.oc, 'live' => pref('live', false) ? true : false, 'dataDate' => Law::DATA_DATE,
        'status' => Law.status, 'snap' => snapshot, 'updateMode' => pref('update_mode', '').to_s,
        'version' => current_version, 'avail' => avail_version, 'snapUrl' => pref('snap_url', DEFAULT_SNAP_URL).to_s
      }
    end

    def self.update_snapshot(manual)
      url = pref('snap_url', DEFAULT_SNAP_URL).to_s.strip
      if url.empty?
        send_js('App.snapMsg', 'ok' => false, 'msg' => '업데이트 주소가 비어 있습니다') if manual
        return
      end
      req = Sketchup::Http::Request.new(url + (url.include?('?') ? '&' : '?') + "t=#{Time.now.to_i}", Sketchup::Http::GET)
      @snap_req = req
      req.start do |_r, res|
        body = res.body.to_s.dup.force_encoding('UTF-8')
        data = JSON.parse(body) rescue nil
        if res.status_code == 200 && data.is_a?(Hash) && data['items']
          File.open(SNAP_FILE, 'w:UTF-8') { |f| f.write(body) }
          set_pref('snap_checked', Time.now.to_i)
          send_js('App.config', config_hash)
          send_js('App.snapMsg', 'ok' => true, 'msg' => "업데이트 완료 (기준 #{data['generated']})") if manual
        elsif manual
          send_js('App.snapMsg', 'ok' => false, 'msg' => "업데이트 실패 (응답 #{res.status_code}). 주소를 확인하세요")
        end
      end
    rescue StandardError => e
      send_js('App.snapMsg', 'ok' => false, 'msg' => "업데이트 실패: #{e.message}") if manual
    end

    def self.current_version
      a = defined?(VERSION) ? VERSION : '0'
      b = pref('installed_version', '0').to_s
      newer?(b, a) ? b : a
    end

    def self.newer?(a, b)
      Gem::Version.new(a.to_s) > Gem::Version.new(b.to_s)
    rescue StandardError
      false
    end

    def self.avail_version
      v = pref('avail_version', '').to_s
      !v.empty? && newer?(v, current_version) ? v : ''
    end

    def self.http_get(url, &blk)
      req = Sketchup::Http::Request.new(url, Sketchup::Http::GET)
      (@http ||= []) << req
      req.start do |r, res|
        @http.delete(r)
        blk.call(res.body.to_s, res.status_code)
      end
    rescue StandardError => e
      blk.call(e.message, 0)
    end

    def self.check_update(manual)
      http_get(REPO_RAW + "version.json?t=#{Time.now.to_i}") do |body, code|
        info = JSON.parse(body.dup.force_encoding('UTF-8')) rescue nil
        unless code == 200 && info && info['version']
          send_js('App.updMsg', 'ok' => false, 'msg' => "버전 확인 실패 (응답 #{code})") if manual
          next
        end
        set_pref('update_checked', Time.now.to_i)
        if newer?(info['version'], current_version)
          set_pref('avail_version', info['version'])
          set_pref('avail_notes', info['notes'].to_s)
          if pref('update_mode', '').to_s == 'auto'
            install_update(info['version'])
          else
            send_js('App.config', config_hash)
            send_js('App.updMsg', 'ok' => true, 'msg' => "새 버전 #{info['version']} 있음. #{info['notes']}") if manual
          end
        elsif manual
          send_js('App.updMsg', 'ok' => true, 'msg' => "최신 버전입니다 (#{current_version})")
        end
      end
    end

    def self.install_update(version = nil)
      version ||= pref('avail_version', '').to_s
      http_get(REPO_RAW + "dist/arch_dims.rbz?t=#{Time.now.to_i}") do |body, code|
        if code != 200 || body.bytesize < 1000 || body[0, 2] != 'PK'
          send_js('App.updMsg', 'ok' => false, 'msg' => "업데이트 파일을 받지 못했습니다 (응답 #{code})")
          next
        end
        begin
          tmp = File.join(Sketchup.temp_dir, 'arch_dims_update.rbz')
          File.open(tmp, 'wb') { |f| f.write(body) }
          Sketchup.install_from_archive(tmp, false)
          set_pref('installed_version', version)
          set_pref('avail_version', '')
          send_js('App.config', config_hash)
          send_js('App.updMsg', 'ok' => true, 'done' => true, 'msg' => "버전 #{version} 설치 완료. 스케치업을 다시 시작하면 적용됩니다")
        rescue Exception => e
          send_js('App.updMsg', 'ok' => false, 'msg' => "설치 실패: #{e.message}")
        end
      end
    end

    def self.send_js(fn, obj)
      @dialog.execute_script("#{fn}(#{JSON.generate(obj)})") if @dialog && @dialog.visible?
    end

    def self.show
      if @dialog && @dialog.visible?
        @dialog.bring_to_front
        return
      end
      @dialog = UI::HtmlDialog.new(
        dialog_title: '건축 치수 사전',
        preferences_key: 'KG_ArchDims',
        scrollable: false,
        width: 1150,
        height: 700,
        min_width: 820,
        min_height: 480,
        style: UI::HtmlDialog::STYLE_DIALOG
      )
      @dialog.set_file(File.join(PLUGIN_DIR, 'ui.html'))
      @dialog.add_action_callback('ready') do |_ctx|
        @dialog.execute_script("App.load(#{payload})")
        send_js('App.config', config_hash)
        update_snapshot(false) if Time.now.to_i - pref('snap_checked', 0).to_i > 86_400
        mode = pref('update_mode', '').to_s
        check_update(false) if !mode.empty? && Time.now.to_i - pref('update_checked', 0).to_i > WEEK
      end
      @dialog.add_action_callback('updCheck') { |_ctx| check_update(true) }
      @dialog.add_action_callback('updInstall') { |_ctx| install_update }
      @dialog.add_action_callback('lawFetch') do |_ctx, json|
        Law.fetch(JSON.parse(json)) { |res| send_js('App.lawResult', res) }
      end
      @dialog.add_action_callback('snapUpdate') { |_ctx| update_snapshot(true) }
      @dialog.add_action_callback('setPref') do |_ctx, json|
        h = JSON.parse(json)
        set_pref('live', h['live'] ? true : false) if h.key?('live')
        set_pref('snap_url', h['snapUrl'].to_s.strip) if h.key?('snapUrl')
        if h.key?('updateMode')
          set_pref('update_mode', h['updateMode'].to_s)
          check_update(false)
        end
        send_js('App.config', config_hash)
      end
      @dialog.add_action_callback('lawCheckAll') do |_ctx, json|
        Law.check_all(JSON.parse(json)) { |res| send_js('App.lawStatus', res) }
      end
      @dialog.add_action_callback('setOC') do |_ctx, v|
        Law.oc = v
        send_js('App.config', config_hash)
      end
      @dialog.add_action_callback('openUrl') { |_ctx, u| UI.openURL(u) }
      @dialog.add_action_callback('close') { |_ctx| @dialog.close }
      @dialog.add_action_callback('saveUser') do |_ctx, json|
        @dialog.execute_script("App.load(#{payload})") if save_user(json)
      end
      @dialog.show
    end

    unless file_loaded?(__FILE__)
      cmd = UI::Command.new('건축 치수 사전') { show }
      cmd.small_icon = File.join(PLUGIN_DIR, 'icons', 'icon_16.png')
      cmd.large_icon = File.join(PLUGIN_DIR, 'icons', 'icon_24.png')
      cmd.tooltip = '건축 치수 사전'
      cmd.status_bar_text = '인체치수·법정치수·권장치수 검색'
      UI.menu('Extensions').add_item(cmd)
      tb = UI::Toolbar.new('건축 치수 사전')
      tb.add_item(cmd)
      tb.restore
      file_loaded(__FILE__)
    end
  end
end
