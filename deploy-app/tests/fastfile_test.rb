require 'minitest/autorun'
require 'tmpdir'
require 'json'
require 'fileutils'

module UI
  def self.user_error!(message); raise message; end
  def self.success(message); end
  def self.important(message); end
end

module Spaceship
  module ConnectAPI
    class Token
      def self.create(**); Struct.new(:text).new('test-token'); end
    end
  end
end

class FastfileHarness
  def self.default_platform(*); end
  def self.platform(*); yield; end
  def self.lane(*); end
  source = File.read(File.expand_path('../app-store-submit', __dir__))
  fastfile = source.split("<<'RUBY'\n", 2).last.split("\nRUBY\n", 2).first
  class_eval(fastfile, 'generated Fastfile')
  alias_method :real_asc_request, :asc_request

  attr_reader :requests
  def initialize(&handler)
    @requests = []
    @handler = handler
  end
  def asc_request(key, method, path, body: nil, allow_not_found: false)
    @requests << [method, path, body]
    @handler.call(method, path, body)
  end
end

class FastfileTest < Minitest::Test
  def with_http(http)
    original = Net::HTTP.method(:start)
    Net::HTTP.define_singleton_method(:start) { |*args, **kwargs, &block| block.call(http) }
    yield
  ensure
    Net::HTTP.define_singleton_method(:start, original)
  end

  def test_missing_lifetime_schedule_is_created_once_and_existing_schedule_is_preserved
    harness = FastfileHarness.new
    harness.define_singleton_method(:asc_request) do |*args, **kwargs|
      real_asc_request(*args, **kwargs)
    end
    priced = false
    creations = 0
    test_case = self
    http = Object.new
    http.define_singleton_method(:request) do |request|
      code, body = case [request.method, request.path.split('?').first]
      when ['GET', '/v2/inAppPurchases/lifetime/relationships/iapPriceSchedule']
        priced ? ['200', { data: { id: 'schedule' } }] : ['404', { errors: [{ code: 'NOT_FOUND' }] }]
      when ['GET', '/v2/inAppPurchases/lifetime/pricePoints']
        ['200', { data: [{ id: 'point', attributes: { customerPrice: '29.99' } }] }]
      when ['POST', '/v1/inAppPurchasePriceSchedules']
        request_body = JSON.parse(request.body)
        local_price_id = request_body.dig('data', 'relationships', 'manualPrices', 'data', 0, 'id')
        test_case.assert_equal '${price1}', local_price_id
        test_case.assert_equal local_price_id, request_body.dig('included', 0, 'id')
        creations += 1
        priced = true
        ['201', { data: { id: 'schedule' } }]
      else
        raise "Unexpected request: #{request.method} #{request.path}"
      end
      response = Net::HTTPResponse::CODE_TO_OBJ.fetch(code).new('1.1', code, '')
      response.define_singleton_method(:body) { JSON.generate(body) }
      response
    end
    with_http(http) do
      2.times { harness.ensure_in_app_purchase_price_schedule({}, product_id: 'lifetime', price: '29.99') }
    end
    assert_equal 1, creations
  end

  def test_optional_missing_relationship_does_not_hide_other_failures
    harness = FastfileHarness.new
    ['403', '404'].each do |code|
      response = Net::HTTPResponse::CODE_TO_OBJ.fetch(code).new('1.1', code, '')
      response.define_singleton_method(:body) { '{"errors":[]}' }
      http = Object.new
      http.define_singleton_method(:request) { |request| response }
      with_http(http) do
        assert_raises(RuntimeError) { harness.real_asc_request({}, :get, '/unrelated') }
        assert_raises(RuntimeError) { harness.real_asc_request({}, :post, '/schedule', allow_not_found: true) }
        if code == '403'
          assert_raises(RuntimeError) { harness.real_asc_request({}, :get, '/schedule', allow_not_found: true) }
        end
      end
    end
  end

  def test_overlong_product_name_is_rejected_before_any_localization_request
    previous = ENV['METADATA_PATH']
    Dir.mktmpdir do |directory|
      ENV['METADATA_PATH'] = directory
      File.write(File.join(directory, 'localizations.json'), JSON.generate({
        'en-US' => { 'subscriptions' => { 'product' => { 'displayName' => 'Valid', 'description' => 'All lessons' } } },
        'de-DE' => { 'subscriptions' => { 'product' => { 'displayName' => 'ü' * 36, 'description' => 'Alle Lektionen' } } }
      }))
      [true, false].each do |subscription|
        harness = FastfileHarness.new { |*| flunk 'Invalid names must not reach Apple' }
        error = assert_raises(RuntimeError) do
          harness.sync_product_localizations(nil, { 'id' => 'id', 'attributes' => { 'productId' => 'product' } }, subscription: subscription)
        end
        assert_includes error.message, 'product (de-DE)'
        assert_includes error.message, '36 characters; maximum is 35'
        assert_empty harness.requests
      end
    end
  ensure
    ENV['METADATA_PATH'] = previous
  end

  def collection(data = [], next_url = nil)
    { 'data' => data, 'links' => { 'next' => next_url } }
  end

  def test_partial_price_failure_can_be_retried_without_recreating_availability
    plan = false
    priced = false
    attempts = 0
    harness = FastfileHarness.new do |method, path, body|
      case [method, path.split('?').first]
      when [:get, '/v1/subscriptions/sub/prices']
        collection(priced ? [{ 'id' => 'price' }] : [])
      when [:get, '/v1/subscriptions/sub/planAvailabilities']
        collection(plan ? [{ 'id' => 'plan', 'attributes' => { 'planType' => 'UPFRONT' } }] : [])
      when [:post, '/v1/subscriptionPlanAvailabilities']
        assert_equal 'UPFRONT', body.dig(:data, :attributes, :planType)
        assert_equal [{ type: 'territories', id: 'USA' }], body.dig(:data, :relationships, :availableTerritories, :data)
        plan = true
        {}
      when [:get, '/v1/subscriptionPlanAvailabilities/plan/availableTerritories']
        collection([{ 'id' => 'USA' }])
      when [:get, '/v1/subscriptions/sub/pricePoints']
        assert_includes path, 'filter[planType]=UPFRONT'
        collection([{ 'id' => 'point', 'attributes' => { 'customerPrice' => '6.99' } }])
      when [:post, '/v1/subscriptionPrices']
        assert plan, 'Plan availability must exist before pricing'
        assert_equal 'point', body.dig(:data, :relationships, :subscriptionPricePoint, :data, :id)
        attempts += 1
        raise 'Simulated pricing failure' if attempts == 1
        priced = true
        {}
      else
        flunk "Unexpected request: #{method} #{path}"
      end
    end
    assert_raises(RuntimeError) { harness.ensure_subscription_price(nil, subscription_id: 'sub', price: '6.99') }
    2.times { harness.ensure_subscription_price(nil, subscription_id: 'sub', price: '6.99') }
    assert_equal 1, harness.requests.count { |method, path, _| method == :post && path == '/v1/subscriptionPlanAvailabilities' }
    assert_equal 2, attempts
  end

  def test_existing_price_is_preserved
    harness = FastfileHarness.new { |*| collection([{ 'id' => 'existing' }]) }
    harness.ensure_subscription_price(nil, subscription_id: 'sub', price: '6.99')
    assert_equal 1, harness.requests.size
    assert_equal :get, harness.requests.first.first
  end

  def test_existing_plan_excluding_usa_is_not_overwritten
    harness = FastfileHarness.new do |method, path, _|
      assert_equal :get, method
      path.include?('/planAvailabilities') ? collection([{ 'id' => 'plan', 'attributes' => { 'planType' => 'UPFRONT' } }]) : collection([{ 'id' => 'CAN' }])
    end
    error = assert_raises(RuntimeError) { harness.ensure_subscription_plan_availability(nil, 'sub', 'UPFRONT') }
    assert_includes error.message, 'Enable USA'
  end

  def test_price_point_lookup_follows_pagination
    harness = FastfileHarness.new do |_, path, _|
      path == '/first' ? collection([], 'https://api.appstoreconnect.apple.com/second') : collection([{ 'id' => 'point', 'attributes' => { 'customerPrice' => '14.99' } }])
    end
    assert_equal 'point', harness.asc_price_point(nil, '/first', '14.99').fetch('id')
    assert_equal 2, harness.requests.size
  end

  def test_group_localizations_resume_after_failure_and_preserve_editorial_defaults
    previous = ENV['METADATA_PATH']
    Dir.mktmpdir do |directory|
      ENV['METADATA_PATH'] = directory
      File.write(File.join(directory, 'localizations.json'), JSON.generate({
        'en-US' => { 'subscriptionGroup' => { 'displayName' => 'Premium Access', 'customAppName' => nil } },
        'de-DE' => { 'appInformation' => { 'name' => 'Koreanisch' } },
        'fr-FR' => { 'subscriptionGroup' => { 'displayName' => 'Accès premium' } }
      }))
      remote = [
        { 'id' => 'en', 'attributes' => { 'locale' => 'en-US', 'name' => 'Old', 'customAppName' => 'Old app' } },
        { 'id' => 'de', 'attributes' => { 'locale' => 'de-DE', 'name' => 'Reviewed name' } }
      ]
      versions = []
      attempts = 0
      harness = FastfileHarness.new do |method, path, body|
        case method
        when :get
          case path
          when '/v1/subscriptionGroups/group/versions?limit=200'
            collection(versions)
          when '/v1/subscriptionGroupVersions/draft/localizations?limit=200'
            collection(remote)
          else
            flunk "Unexpected GET: #{path}"
          end
        when :patch
          assert_equal '/v2/subscriptionGroupLocalizations/en', path
          remote.first['attributes'].merge!(body[:data][:attributes].transform_keys(&:to_s))
          {}
        when :post
          if path == '/v1/subscriptionGroupVersions'
            assert_equal({ type: 'subscriptionGroups', id: 'group' }, body.dig(:data, :relationships, :subscriptionGroup, :data))
            versions << { 'id' => 'draft', 'attributes' => { 'state' => 'PREPARE_FOR_SUBMISSION' } }
            { 'data' => versions.first }
          else
            assert_equal '/v2/subscriptionGroupLocalizations', path
            assert_equal({ type: 'subscriptionGroupVersions', id: 'draft' }, body.dig(:data, :relationships, :version, :data))
            refute body[:data][:attributes].key?(:customAppName)
            attempts += 1
            raise 'Temporary failure' if attempts == 1
            remote << { 'id' => 'fr', 'attributes' => body[:data][:attributes].transform_keys(&:to_s) }
            {}
          end
        end
      end
      assert_raises(RuntimeError) { harness.sync_subscription_group_localizations(nil, { 'id' => 'group' }) }
      2.times { harness.sync_subscription_group_localizations(nil, { 'id' => 'group' }) }
      assert_equal 1, harness.requests.count { |method, _, _| method == :patch }
      assert_equal 2, attempts
      assert_nil remote.first['attributes']['customAppName']
      assert_equal 'Reviewed name', remote[1]['attributes']['name']
    end
  ensure
    ENV['METADATA_PATH'] = previous
  end

  def test_group_localizations_fill_missing_locale_with_localized_app_name
    previous = ENV['METADATA_PATH']
    Dir.mktmpdir do |directory|
      ENV['METADATA_PATH'] = directory
      File.write(File.join(directory, 'localizations.json'), JSON.generate({
        'de-DE' => { 'appInformation' => { 'name' => 'Koreanisch TOPIK I' } }
      }))
      harness = FastfileHarness.new do |method, path, body|
        case [method, path]
        when [:get, '/v1/subscriptionGroups/group/versions?limit=200'],
             [:get, '/v1/subscriptionGroupVersions/draft/localizations?limit=200']
          collection
        when [:post, '/v1/subscriptionGroupVersions']
          assert_equal({ type: 'subscriptionGroups', id: 'group' }, body.dig(:data, :relationships, :subscriptionGroup, :data))
          { 'data' => { 'id' => 'draft', 'attributes' => { 'state' => 'PREPARE_FOR_SUBMISSION' } } }
        when [:post, '/v2/subscriptionGroupLocalizations']
          assert_equal({ name: 'Koreanisch TOPIK I', locale: 'de-DE' }, body[:data][:attributes])
          assert_equal({ type: 'subscriptionGroupVersions', id: 'draft' }, body.dig(:data, :relationships, :version, :data))
          {}
        else
          flunk "Unexpected request: #{method} #{path}"
        end
      end
      harness.sync_subscription_group_localizations(nil, { 'id' => 'group' })
      assert_equal 4, harness.requests.size
    end
  ensure
    ENV['METADATA_PATH'] = previous
  end

  def test_group_localizations_validate_all_entries_before_writing
    previous = ENV['METADATA_PATH']
    Dir.mktmpdir do |directory|
      ENV['METADATA_PATH'] = directory
      [nil, {}, { 'displayName' => ' ' }, { 'displayName' => 'x' * 76 },
       { 'displayName' => 'Access', 'customAppName' => 'x' * 31 }].each do |invalid|
        File.write(File.join(directory, 'localizations.json'), JSON.generate({
          'en-US' => { 'subscriptionGroup' => { 'displayName' => 'Access' } },
          'de-DE' => { 'subscriptionGroup' => invalid }
        }))
        harness = FastfileHarness.new { |*| flunk 'Invalid input must not contact Apple' }
        assert_raises(RuntimeError) { harness.sync_subscription_group_localizations(nil, { 'id' => 'group' }) }
        assert_empty harness.requests
      end
    end
  ensure
    ENV['METADATA_PATH'] = previous
  end

  def test_product_localizations_create_update_and_skip_unchanged
    previous = ENV['METADATA_PATH']
    Dir.mktmpdir do |directory|
      ENV['METADATA_PATH'] = directory
      File.write(File.join(directory, 'localizations.json'), JSON.generate({
        'en-US' => { 'subscriptions' => { 'product' => { 'displayName' => 'Access', 'description' => 'All lessons' } } },
        'de-DE' => { 'subscriptions' => { 'product' => { 'displayName' => 'Zugang', 'description' => 'Alle Lektionen' } } }
      }))
      [true, false].each do |subscription|
        remote = [{ 'id' => 'existing', 'attributes' => { 'locale' => 'en-US', 'name' => 'Old', 'description' => 'Old' } }]
        version_type = subscription ? 'subscriptionVersions' : 'inAppPurchaseVersions'
        versions = [{ 'id' => 'draft', 'attributes' => { 'state' => 'PREPARE_FOR_SUBMISSION' } }]
        harness = FastfileHarness.new do |method, path, body|
          case method
          when :get
            if path.end_with?('/versions?limit=200')
              collection(versions)
            else
              assert_equal "/v1/#{version_type}/draft/localizations?limit=200", path
              collection(remote)
            end
          when :patch
            assert_equal "/v2/#{subscription ? 'subscriptionLocalizations' : 'inAppPurchaseLocalizations'}/existing", path
            remote.first['attributes'].merge!(body.fetch(:data).fetch(:attributes).transform_keys(&:to_s))
            {}
          when :post
            assert_equal({ type: version_type, id: 'draft' }, body.dig(:data, :relationships, :version, :data))
            remote << { 'id' => 'new', 'attributes' => body.fetch(:data).fetch(:attributes).transform_keys(&:to_s) }
            {}
          end
        end
        product = { 'id' => 'remote-product', 'attributes' => { 'productId' => 'product' } }
        2.times { harness.sync_product_localizations(nil, product, subscription: subscription) }
        assert_equal 1, harness.requests.count { |method, _, _| method == :post }
        assert_equal 1, harness.requests.count { |method, _, _| method == :patch }
      end
    end
  ensure
    ENV['METADATA_PATH'] = previous
  end

  def test_default_products_create_lifetime_with_valid_attributes_and_reuse_it_on_retry
    environment = {
      'IAP_CREATE_DEFAULTS' => '1',
      'METADATA_PATH' => Dir.mktmpdir,
      'IAP_SUBSCRIPTION_GROUP_NAME' => 'Premium Access',
      'IAP_MONTHLY_REFERENCE_NAME' => 'Monthly',
      'IAP_MONTHLY_PRODUCT_ID' => 'product.monthly',
      'IAP_MONTHLY_PRICE_USD' => '6.99',
      'IAP_QUARTERLY_REFERENCE_NAME' => 'Quarterly',
      'IAP_QUARTERLY_PRODUCT_ID' => 'product.quarterly',
      'IAP_QUARTERLY_PRICE_USD' => '14.99',
      'IAP_LIFETIME_REFERENCE_NAME' => 'Lifetime',
      'IAP_LIFETIME_PRODUCT_ID' => 'product.lifetime',
      'IAP_LIFETIME_PRICE_USD' => ''
    }
    previous = environment.keys.to_h { |key| [key, ENV[key]] }
    ENV.update(environment)

    lifetime = nil
    harness = FastfileHarness.new do |method, path, body|
      case [method, path]
      when [:get, '/v1/apps/app/subscriptionGroups?limit=200']
        collection([{ 'id' => 'group', 'attributes' => { 'referenceName' => 'Premium Access' } }])
      when [:get, '/v1/subscriptionGroups/group/subscriptions?limit=200']
        collection([
          { 'id' => 'monthly', 'attributes' => { 'productId' => 'product.monthly' } },
          { 'id' => 'quarterly', 'attributes' => { 'productId' => 'product.quarterly' } }
        ])
      when [:get, '/v1/subscriptions/monthly/prices?filter[territory]=USA&filter[planType]=UPFRONT&limit=200'],
           [:get, '/v1/subscriptions/quarterly/prices?filter[territory]=USA&filter[planType]=UPFRONT&limit=200']
        collection([{ 'id' => 'existing-price' }])
      when [:get, '/v1/apps/app/inAppPurchasesV2?limit=200']
        collection(lifetime ? [lifetime] : [])
      when [:post, '/v2/inAppPurchases']
        assert_equal 'inAppPurchases', body.dig(:data, :type)
        assert_equal({
          name: 'Lifetime', productId: 'product.lifetime',
          inAppPurchaseType: 'NON_CONSUMABLE',
          reviewNote: "In order to see the \"Unlock Premium\":\n\n1. Open the app\n2. Open \"Verb Conjugation\"\n3. Scroll until 3rd word\n4. Click on any part with the \"lock\" icon"
        }, body.dig(:data, :attributes))
        assert_equal({ app: { data: { type: 'apps', id: 'app' } } }, body.dig(:data, :relationships))
        lifetime = { 'id' => 'lifetime', 'attributes' => { 'productId' => 'product.lifetime' } }
        { 'data' => lifetime }
      else
        flunk "Unexpected request: #{method} #{path}"
      end
    end

    2.times { harness.ensure_default_products(nil, Struct.new(:id).new('app')) }
    assert_equal 1, harness.requests.count { |method, path, _| method == :post && path == '/v2/inAppPurchases' }
    assert_includes harness.requests.map { |method, path, _| [method, path] }, [:get, '/v1/apps/app/inAppPurchasesV2?limit=200']
  ensure
    previous&.each { |key, value| ENV[key] = value }
    FileUtils.remove_entry(environment['METADATA_PATH']) if environment && File.directory?(environment['METADATA_PATH'])
  end

  def test_submitted_subscription_in_another_group_is_reused_without_duplicate_post
    environment = {
      'IAP_CREATE_DEFAULTS' => '1',
      'METADATA_PATH' => Dir.mktmpdir,
      'IAP_SUBSCRIPTION_GROUP_NAME' => 'Premium Access',
      'IAP_MONTHLY_REFERENCE_NAME' => 'Monthly',
      'IAP_MONTHLY_PRODUCT_ID' => 'product.monthly',
      'IAP_MONTHLY_PRICE_USD' => '6.99',
      'IAP_QUARTERLY_REFERENCE_NAME' => 'Quarterly',
      'IAP_QUARTERLY_PRODUCT_ID' => 'product.quarterly',
      'IAP_QUARTERLY_PRICE_USD' => '14.99',
      'IAP_LIFETIME_REFERENCE_NAME' => 'Lifetime',
      'IAP_LIFETIME_PRODUCT_ID' => 'product.lifetime',
      'IAP_LIFETIME_PRICE_USD' => ''
    }
    previous = environment.keys.to_h { |key| [key, ENV[key]] }
    ENV.update(environment)

    submitted_monthly = { 'id' => 'submitted-monthly', 'attributes' => { 'productId' => 'product.monthly' } }
    lifetime = { 'id' => 'lifetime', 'attributes' => { 'productId' => 'product.lifetime' } }
    harness = FastfileHarness.new do |method, path, body|
      case [method, path]
      when [:get, '/v1/apps/app/subscriptionGroups?limit=200']
        collection([
          { 'id' => 'current-group', 'attributes' => { 'referenceName' => 'Premium Access' } },
          { 'id' => 'submitted-group', 'attributes' => { 'referenceName' => 'Previous Access' } }
        ])
      when [:get, '/v1/subscriptionGroups/current-group/subscriptions?limit=200']
        collection([])
      when [:get, '/v1/subscriptionGroups/submitted-group/subscriptions?limit=200']
        collection([submitted_monthly])
      when [:get, '/v1/subscriptions/submitted-monthly/prices?filter[territory]=USA&filter[planType]=UPFRONT&limit=200']
        collection([{ 'id' => 'existing-price' }])
      when [:post, '/v1/subscriptions']
        assert_equal 'product.quarterly', body.dig(:data, :attributes, :productId)
        { 'data' => { 'id' => 'quarterly', 'attributes' => { 'productId' => 'product.quarterly' } } }
      when [:get, '/v1/subscriptions/quarterly/prices?filter[territory]=USA&filter[planType]=UPFRONT&limit=200']
        collection([{ 'id' => 'existing-price' }])
      when [:get, '/v1/apps/app/inAppPurchasesV2?limit=200']
        collection([lifetime])
      else
        flunk "Unexpected request: #{method} #{path}"
      end
    end

    harness.ensure_default_products(nil, Struct.new(:id).new('app'))
    assert_equal 1, harness.requests.count { |method, path, _| method == :post && path == '/v1/subscriptions' }
    refute harness.requests.any? { |method, path, body| method == :post && path == '/v1/subscriptions' && body.dig(:data, :attributes, :productId) == 'product.monthly' }
  ensure
    previous&.each { |key, value| ENV[key] = value }
    FileUtils.remove_entry(environment['METADATA_PATH']) if environment && File.directory?(environment['METADATA_PATH'])
  end

  def test_inline_in_app_purchase_price_matches_apple_resource_schema
    harness = FastfileHarness.new do |method, path, body|
      case [method, path]
      when [:get, '/price-points']
        collection([{ 'id' => 'price-point', 'attributes' => { 'customerPrice' => '29.99' } }])
      when [:post, '/v1/inAppPurchasePriceSchedules']
        local_price_id = body.dig(:data, :relationships, :manualPrices, :data, 0, :id)
        assert_equal '${price1}', local_price_id
        assert_equal local_price_id, body.dig(:included, 0, :id)
        assert_equal 'inAppPurchasePriceSchedules', body.dig(:data, :type)
        refute body.fetch(:data).key?(:attributes)
        assert_equal({ type: 'inAppPurchases', id: '6816897818' }, body.dig(:data, :relationships, :inAppPurchase, :data))
        assert_equal({ type: 'territories', id: 'USA' }, body.dig(:data, :relationships, :baseTerritory, :data))
        assert_equal 'inAppPurchasePrices', body.dig(:included, 0, :type)
        assert_equal({ type: 'inAppPurchases', id: '6816897818' }, body.dig(:included, 0, :relationships, :inAppPurchaseV2, :data))
        assert_equal({ type: 'inAppPurchasePricePoints', id: 'price-point' }, body.dig(:included, 0, :relationships, :inAppPurchasePricePoint, :data))
        {}
      else
        flunk "Unexpected request: #{method} #{path}"
      end
    end

    harness.create_in_app_purchase_price_schedule(nil, product_id: '6816897818', price: '29.99', price_points_path: '/price-points')
  end
end
