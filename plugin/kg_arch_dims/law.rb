require 'json'
require 'uri'

module KG
  module ArchDims
    module Law
      BASE = 'https://www.law.go.kr/DRF/'
      DATA_DATE = '20261120'
      PREF = 'KG_ArchDims'
      DAY = 86_400

      class << self
        attr_writer :cache_file

        def oc
          Sketchup.read_default(PREF, 'oc', '').to_s
        end

        def oc=(v)
          Sketchup.write_default(PREF, 'oc', v.to_s.strip)
          @cache = {}
          save_cache
        end

        def cache
          @cache ||= begin
            File.exist?(@cache_file.to_s) ? JSON.parse(File.read(@cache_file, encoding: 'UTF-8')) : {}
          rescue StandardError
            {}
          end
        end

        def save_cache
          return unless @cache_file
          File.open(@cache_file, 'w:UTF-8') { |f| f.write(JSON.generate(cache)) }
        rescue StandardError
          nil
        end

        def cached(key, ttl)
          e = cache[key]
          e && Time.now.to_i - e['t'].to_i < ttl ? e['d'] : nil
        end

        def store(key, data)
          cache[key] = { 't' => Time.now.to_i, 'd' => data }
          save_cache
          data
        end

        def norm(s)
          s.to_s.gsub(/[\s·ㆍ・‧]/, '')
        end

        def parse_src(src)
          s = src.to_s.strip
          info = {}
          if (m = s.match(/\s*별표\s*(\d+)(?:의\s*(\d+))?\s*$/))
            info[:byul] = [m[1].to_i, m[2].to_i]
            s = s[0...m.begin(0)]
          end
          if (m = s.match(/\s*제\s*(\d+)\s*조(?:\s*의\s*(\d+))?\s*$/))
            info[:jo] = [m[1].to_i, m[2].to_i]
            s = s[0...m.begin(0)]
          end
          s = s.sub(/\s*\([^)]*\)\s*$/, '').strip
          info[:name] = s
          info[:kind] = s =~ /(법|법률|시행령|시행규칙|규칙|규정)$/ ? 'law' : 'admrul'
          info
        end

        def get(path, params, &blk)
          url = BASE + path + '?' + URI.encode_www_form({ 'OC' => oc, 'type' => 'JSON' }.merge(params))
          if defined?(Sketchup::Http::Request)
            req = Sketchup::Http::Request.new(url, Sketchup::Http::GET)
            (@reqs ||= []) << req
            req.start do |r, res|
              @reqs.delete(r)
              handle(res.body.to_s.dup.force_encoding('UTF-8'), res.status_code, &blk)
            end
          else
            require 'net/http'
            res = Net::HTTP.get_response(URI(url))
            handle(res.body.to_s.dup.force_encoding('UTF-8'), res.code.to_i, &blk)
          end
        rescue StandardError => e
          blk.call(nil, "연결 실패: #{e.message}")
        end

        def handle(body, code)
          data = begin
            JSON.parse(body)
          rescue StandardError
            nil
          end
          if data.nil?
            msg = clean(body)[0, 160]
            yield nil, "응답 오류(#{code}) #{msg}"
          elsif data.is_a?(Hash) && data['result'] && data.size <= 3 && data['result'].to_s.include?('실패')
            yield nil, auth_msg(data)
          else
            yield data, nil
          end
        end

        def auth_msg(data)
          "#{data['result']} #{data['msg']}".strip +
            ' (법제처 OPEN API는 신청할 때 등록한 IP에서만 응답합니다. 지금 PC의 공인 IP가 등록돼 있는지, 신청이 승인됐는지 확인하세요.)'
        end

        def each_hash(o, &b)
          case o
          when Hash
            b.call(o)
            o.each_value { |v| each_hash(v, &b) }
          when Array
            o.each { |v| each_hash(v, &b) }
          end
        end

        def texts(o, inside = false, acc = [])
          case o
          when Hash
            o.each do |k, v|
              hit = k.to_s.end_with?('내용')
              if v.is_a?(String)
                acc << v if hit
              else
                texts(v, hit, acc)
              end
            end
          when Array
            o.each { |v| v.is_a?(String) ? (acc << v if inside) : texts(v, inside, acc) }
          end
          acc
        end

        def clean(s)
          s.to_s.gsub(/<br\s*\/?>/i, "\n").gsub(/<[^>]+>/, '')
           .gsub('&nbsp;', ' ').gsub('&lt;', '<').gsub('&gt;', '>').gsub('&amp;', '&').gsub('&quot;', '"')
           .gsub(/[ \t]+/, ' ').gsub(/\n\s*\n+/, "\n").strip
        end

        def find_law(name, &done)
          key = "s:#{norm(name)}"
          if (hit = cached(key, DAY))
            return done.call(hit, nil)
          end
          search_law(name, name.tr('·・‧', 'ㆍㆍㆍ'), true, &done)
        end

        def search_law(name, query, retry_once, &done)
          key = "s:#{norm(name)}"
          get('lawSearch.do', 'target' => 'law', 'query' => query, 'display' => '50') do |data, err|
            next done.call(nil, err) unless data
            list = []
            each_hash(data) { |h| list << h if h['법령명한글'] }
            pick = list.find { |h| norm(h['법령명한글']) == norm(name) } ||
                   list.find { |h| norm(h['법령명한글']).include?(norm(name)) }
            unless pick
              next search_law(name, name.gsub(/[·ㆍ・‧]/, ' ').split.first(3).join(' '), false, &done) if retry_once
              next done.call(nil, "'#{name}' 법령을 찾지 못했습니다")
            end
            done.call(store(key, {
              'name' => pick['법령명한글'], 'mst' => pick['법령일련번호'].to_s, 'id' => pick['법령ID'].to_s,
              'eff' => pick['시행일자'].to_s, 'prom' => pick['공포일자'].to_s
            }), nil)
          end
        end

        def jo_title(h)
          no = h['조문번호'].to_i
          g = h['조문가지번호'].to_i
          t = "제#{no}조#{g > 0 ? "의#{g}" : ''}"
          h['조문제목'].to_s.empty? ? t : "#{t}(#{h['조문제목']})"
        end

        def jo_units(data)
          list = []
          each_hash(data) { |h| list << h if h.key?('조문번호') && h['조문여부'].to_s != '전문' }
          list
        end

        def article(data, jo)
          u = jo_units(data).find { |h| h['조문번호'].to_i == jo[0] && h['조문가지번호'].to_i == jo[1] }
          u ? [{ 'title' => jo_title(u), 'text' => clean(texts(u).join("\n")) }] : []
        end

        def hint_articles(data, hints)
          hs = Array(hints).map(&:to_s).reject { |x| x.length < 2 }.uniq
          scored = jo_units(data).map do |h|
            title = h['조문제목'].to_s
            body = texts(h).join(' ')
            s = hs.sum { |w| (title.include?(w) ? 5 : 0) + (body.include?(w) ? 1 : 0) }
            [s, h]
          end
          scored.select { |s, _| s > 0 }.sort_by { |s, _| -s }.first(2).map do |_, h|
            { 'title' => jo_title(h), 'text' => clean(texts(h).join("\n")) }
          end
        end

        def byul(data, b)
          list = []
          each_hash(data) { |h| list << h if h.key?('별표번호') }
          u = list.find { |h| h['별표번호'].to_i == b[0] && h['별표가지번호'].to_i == b[1] && h['별표구분'].to_s != '서식' } ||
              list.find { |h| h['별표번호'].to_i == b[0] }
          return [] unless u
          title = "별표 #{b[0]}#{b[1] > 0 ? "의#{b[1]}" : ''} #{u['별표제목']}".strip
          [{ 'title' => title, 'text' => clean(texts(u).join("\n")) }]
        end

        def web_url(name, info)
          seg = "법령/#{name.delete(' ')}"
          if info[:jo]
            seg += "/제#{info[:jo][0]}조#{info[:jo][1] > 0 ? "의#{info[:jo][1]}" : ''}"
          end
          'https://www.law.go.kr/' + seg.split('/').map { |x| URI.encode_www_form_component(x).gsub('+', '%20') }.join('/')
        end

        def fetch(req, &done)
          info = parse_src(req['src'])
          base = { 'id' => req['id'], 'src' => req['src'] }
          return fetch_admrul(info, base, &done) if info[:kind] == 'admrul'
          rkey = "r:#{req['src']}|#{Array(req['hints']).join(',')}"
          return done.call(base.merge('ok' => false, 'error' => '인증키(OC)가 설정되지 않았습니다')) if oc.empty?
          if !req['force'] && (hit = cached(rkey, 3 * DAY))
            return done.call(base.merge(hit))
          end
          find_law(info[:name]) do |law, err|
            next done.call(base.merge('ok' => false, 'error' => err)) unless law
            params = { 'target' => 'law', 'MST' => law['mst'] }
            params['JO'] = format('%04d%02d', *info[:jo]) if info[:jo] && !info[:byul]
            get('lawService.do', params) do |data, err2|
              next done.call(base.merge('ok' => false, 'error' => err2)) unless data
              items = if info[:byul] then byul(data, info[:byul])
                      elsif info[:jo] then article(data, info[:jo])
                      else hint_articles(data, req['hints'])
                      end
              res = {
                'ok' => true, 'law' => law['name'], 'eff' => law['eff'], 'prom' => law['prom'],
                'items' => items, 'url' => web_url(law['name'], info),
                'changed' => law['eff'].to_s > DATA_DATE, 'checked' => Time.now.strftime('%Y%m%d')
              }
              res['error'] = '해당 조문을 응답에서 찾지 못했습니다. 법령 사이트에서 확인하세요.' if items.empty?
              done.call(base.merge(items.empty? ? res : store(rkey, res)))
            end
          end
        end

        def fetch_admrul(info, base, &done)
          return done.call(base.merge('ok' => false, 'error' => '인증키(OC)가 설정되지 않았습니다')) if oc.empty?
          get('lawSearch.do', 'target' => 'admrul', 'query' => info[:name], 'display' => '10') do |data, err|
            next done.call(base.merge('ok' => false, 'error' => err)) unless data
            list = []
            each_hash(data) { |h| list << h if h['행정규칙명'] }
            items = list.first(6).map do |h|
              link = h['행정규칙상세링크'].to_s
              { 'title' => h['행정규칙명'].to_s, 'text' => "시행 #{h['시행일자']} · #{h['행정규칙종류']}".strip,
                'url' => link.empty? ? nil : 'https://www.law.go.kr' + link.sub(/OC=[^&]*/, "OC=#{oc}").sub('type=XML', 'type=HTML') }
            end
            done.call(base.merge('ok' => true, 'admrul' => true, 'law' => info[:name], 'items' => items,
                                 'url' => 'https://www.law.go.kr/행정규칙/' + URI.encode_www_form_component(info[:name].delete(' ')),
                                 'error' => items.empty? ? '행정규칙 검색 결과가 없습니다' : nil))
          end
        end

        def check_all(names, &done)
          names = Array(names).uniq.select { |n| parse_src(n)[:kind] == 'law' }
          status = {}
          errors = []
          step = lambda do |i|
            if i >= names.size
              cache['status'] = { 'at' => Time.now.strftime('%Y%m%d %H:%M'), 'laws' => status }
              save_cache
              next done.call('ok' => errors.empty? || !status.empty?, 'status' => cache['status'], 'errors' => errors.uniq.first(3))
            end
            nm = parse_src(names[i])[:name]
            cache.delete("s:#{norm(nm)}")
            find_law(nm) do |law, err|
              if law
                status[norm(nm)] = { 'name' => law['name'], 'eff' => law['eff'], 'changed' => law['eff'].to_s > DATA_DATE }
              else
                errors << err
                if err.to_s.include?('검증')
                  cache['status'] = { 'at' => Time.now.strftime('%Y%m%d %H:%M'), 'laws' => status }
                  next done.call('ok' => false, 'status' => cache['status'], 'errors' => [err])
                end
              end
              UI.start_timer(0.15, false) { step.call(i + 1) }
            end
          end
          step.call(0)
        end

        def status
          cache['status']
        end
      end
    end
  end
end
